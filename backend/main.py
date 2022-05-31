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
        self.time = datetime.fromisoformat(timestamp)


# load discord token from .env 
load_dotenv()
token = os.getenv("DISCORD_TOKEN")

# average sentiment of other users with referring to this user
sentiments = {'Donuts': {'mossy': 0.7, 'Knuck': 0.5}, 'mossy': {'Donuts': 0.3, 'Knuck': 0.6}, 'Knuck': {'Donuts': -0.9, 'mossy': 0.5}}

# each user and the message id of the message with the most sentiment
max_sentiments = {'Donuts': 1792387123, 'mossy': 123871923, 'Knuck': 12731023}

# each user and the message id of the message with the least sentiment
min_sentiments = {'Donuts': 28713941234, 'mossy': 71928347891234, 'Knuck': 18029348912}

# returns all messages in the channel
def get_messages(limit=5):
    # regex to find links in messages (https://daringfireball.net/2010/07/improved_regex_for_matching_urls)
    link_regex = r"(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    
    messages = []
    last_msg = None

    while True:
        request = requests.get(f"https://discord.com/api/channels/979554513021177909/messages?limit=100&before={last_msg}" if last_msg else "https://discord.com/api/channels/979554513021177909/messages?limit=100", headers={'Authorization': f'Bot {token}'})

        # if rate limited, wait "retry_after" seconds
        if request.status_code == 429:
            time.sleep(float(request.headers["retry-after"]) / 1000)
            continue
        
        data = request.json()

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
            unmarked_msg = unmark(message['content'])

            # make sure there are no links
            if len(re.findall(link_regex, unmarked_msg)) != 0:
                continue

            print(message['content'])
            messages.append(Message(unmarked_msg, message['id'], message['author']['id'], message['timestamp']))

            # stop once message limit has been reached
            if len(messages) >= limit:
                break
        
        # update id of last message
        last_msg = data[-1]['id']
    
    return messages

# creates clusters of messages based on time frame to prepare for coref
def cluster(messages):
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
                clusters.append(cluster)
                cluster = []
            
            cluster.append(message)
    
    # add last cluster
    if len(cluster) != 0:
        clusters.append(cluster)

    return clusters


# possibly prepend each message with "user said" and append each message with "i you he she" to help coreference?
def coref():
    pass

messages = get_messages(limit=100)
print()

for _cluster in cluster(messages):
    for message in _cluster:
        print(message.content)
    print()