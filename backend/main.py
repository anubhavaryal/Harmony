import os
from dotenv import load_dotenv
import spacy
import neuralcoref
import requests
import time
import re
from datetime import datetime, timedelta
from markdown import Markdown
from io import StringIO

# TODO: remove spoiler and code block markdown from messages

# patch markdown (code snippet from https://stackoverflow.com/a/54923798)
def unmark_element(element, stream=None):
    if stream is None:
        stream = StringIO()
    if element.text:
        stream.write(element.text)
    for sub in element:
        unmark_element(sub, stream)
    if element.tail:
        stream.write(element.tail)
    return stream.getvalue()


Markdown.output_formats["plain"] = unmark_element
__md = Markdown(output_format="plain")
__md.stripTopLevelTags = False


# remove markdown from text
def unmark(text):
    return __md.convert(text)


# class to store each discord message
class Message:
    def __init__(self, content, message_id, user_id, timestamp):
        self.content = content
        self.message_id = message_id
        self.user_id = user_id
        self.timestamp = timestamp
        self.time = datetime.fromisoformat(timestamp)


# load discord token from .env 
load_dotenv()
token = os.getenv("DISCORD_TOKEN")

# load nlp
nlp = spacy.load('en_core_web_sm')
neuralcoref.add_to_pipe(nlp, blacklist=False)

# average sentiment of other users with referring to this user
sentiments = {'Donuts': {'mossy': 0.7, 'Knuck': 0.5}, 'mossy': {'Donuts': 0.3, 'Knuck': 0.6}, 'Knuck': {'Donuts': -0.9, 'mossy': 0.5}}

# each user and the message id of the message with the most sentiment
max_sentiments = {'Donuts': 1792387123, 'mossy': 123871923, 'Knuck': 12731023}

# each user and the message id of the message with the least sentiment
min_sentiments = {'Donuts': 28713941234, 'mossy': 71928347891234, 'Knuck': 18029348912}

# cache users
users = {}


# returns json associated with request to discord api
def send_request(url, headers={}):
    request = requests.get(f"https://discord.com/api{url}", headers=headers)

    # if rate limited, wait "retry_after" seconds
    while request.status_code == 429:
        time.sleep(float(request.headers["retry-after"]) / 1000)
    
    return request.json()


# finds and returns user using the matched mention
def get_user_from_mention(match):
    # get user id from mention
    user_id = match.group(1)

    # if the user has been cached
    if user_id in users:
        return users[user_id]
    
    # find and cache user
    data = send_request(f"/users/{user_id}", headers={'Authorization': f'Bot {token}'})
    users[user_id] = data['username']

    return data['username']

    
# returns all messages in the channel
def get_messages(limit=5):
    # regex to find links in messages (https://daringfireball.net/2010/07/improved_regex_for_matching_urls)
    link_regex = r"(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    
    # regex to find mentions in messages
    mention_regex = r"<@!?(\d+)>"

    # min and max size of messages
    min_size = 8
    max_size = 50

    messages = []
    last_msg = None

    while True:
        data = send_request(f"/channels/979554513021177909/messages?limit=100&before={last_msg}" if last_msg else "/channels/979554513021177909/messages?limit=100", headers={'Authorization': f'Bot {token}'})

        # break out of loop once there are no more messages
        if not data:
            break
        
        for message in data:
            # make sure message type is 0 (DEFAULT)
            if message['type'] != 0:
                continue

            # make sure there are no attachments
            if message['attachments']:
                continue

            # remove markdown from content
            msg = unmark(message['content'])

            # make sure there are no links
            if len(re.findall(link_regex, msg)) != 0:
                continue

            # replace mentions with respective user
            msg = re.sub(mention_regex, get_user_from_mention, msg)

            # make sure message is within min/max
            if len(msg) < min_size or len(message) > max_size:
                continue

            messages.append(Message(msg, message['id'], message['author']['id'], message['timestamp']))

            # stop once message limit has been reached
            if len(messages) >= limit:
                break
        
        # update id of last message
        last_msg = data[-1]['id']
    
    return messages


# creates clusters of messages based on time frame to prepare for coref
def create_clusters(messages):
    # max amount of time between start message and last message in the cluster
    max_dist = timedelta(minutes=5)

    # max amount of time between consecutive messages in the cluster
    dist = timedelta(minutes=1)

    # stores all message clusters
    clusters = []

    # stores current cluster
    cluster = []
    
    for message in messages:
        if len(cluster) == 0:
            # add message to cluster if it is empty
            cluster.append(message)
        else:
            # find time difference between message and first/last cluster messages
            first_delta = cluster[0].time - message.time
            last_delta = cluster[-1].time - message.time

            # if time difference too large/surpasses max dist, create new cluster
            if last_delta > dist or first_delta > max_dist:
                cluster.reverse()
                clusters.append(cluster)
                cluster = []
            
            cluster.append(message)
    
    # add last cluster
    if len(cluster) != 0:
        cluster.reverse()
        clusters.append(cluster)

    return clusters


# resolves coreferences in message clusters
def coref(clusters):
    messages = []

    # pattern matches "username said "
    user_pattern = re.compile(r"^.+ said $")

    for cluster in clusters:
        # combine all messages in cluster to assist with coreference resolution
        cluster_message = u""

        for message in cluster:
            # prepare message
            content = users[message.user_id]  + ' said "' + message.content.replace('"', '\'') + '." '
            cluster_message += content
        
        # resolve coreferences
        doc = nlp(cluster_message)

        # dissolve cluster message
        new_messages = [i[:-1] for i in doc._.coref_resolved.split('"') if not user_pattern.match(i)]
        del new_messages[-1]

        for (message, new_message) in zip(cluster, new_messages):
            messages.append(Message(new_message, message.message_id, message.user_id, message.timestamp))
    
    return messages

# sentiment analysis on entities
def sentiment(messages):
    # create groups of messages to send through api (1000 characters = 1 unit)
    content = ""

    for message in messages:
        # prepare message by removing dots
        clean_message = message.content.translate({ord(c): None for c in '.'})

        # add message to current group if character limit not reached
        if len(clean_message) + len(content) < 1000:
            content += clean_message + ". "

    return content


if __name__ == "__main__":
    messages = get_messages(limit=100)
    print(len(messages))
    messages = coref(create_clusters(messages))
    messages = sentiment(messages)

    print(messages)
    print(len(messages))