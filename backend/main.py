import os
from dotenv import load_dotenv
import spacy
import neuralcoref
import requests
import time
import re
from datetime import datetime, timedelta
from google.cloud import language_v1

# TODO: handle messages with emojis

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

# instantiate google client
# client = language_v1.LanguageServiceClient()
type_ = language_v1.types.Document.Type.PLAIN_TEXT
language = "en"
encoding_type = language_v1.EncodingType.UTF8

# dict of users for their respective user_id's
users = {'240833127713472513': 'Donuts'}


# returns json associated with request to discord api
def send_request(url, headers={}):
    request = requests.get(f"https://discord.com/api{url}", headers=headers)

    # if rate limited, wait "retry_after" seconds
    while request.status_code == 429:
        time.sleep(float(request.headers["retry-after"]) / 1000)
    
    return request.json()


# find and returns user with the given id
def get_user_by_id(user_id):
    # if the user has been cached
    if user_id in users:
        return users[user_id]
    
    # find and cache user
    data = send_request(f"/users/{user_id}", headers={'Authorization': f'Bot {token}'})
    users[user_id] = data['username']

    return data['username']
    

# prepares Discord message object for analysis
def prepare_message(message):
    # min and max length of messages
    min_size = 8
    max_size = 50

    # regex to find links in messages (https://daringfireball.net/2010/07/improved_regex_for_matching_urls)
    link_regex = r"(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    mention_regex = r"<@!?(\d+)>"  # regex to find mentions in messages
    code_regex = r"```.+\n.*\n```"  # regex to find code blocks
    special_chars_regex = r"[^A-Za-z0-9\'\" ]+"  # regex to find special characters (not alphanumeric, quotes, or space)

    # finds and returns user using the matched mention
    def get_user_from_mention(match):
        # get user id from mention
        user_id = match.group(1)

        return get_user_by_id(user_id)


    # ensure message type is 0 (DEFAULT)
    if message['type'] != 0:
        return
    
    # ensure there are no attachments
    if message['attachments']:
        return

    # ignore messages with code blocks
    if len(re.findall(code_regex, message['content'])) != 0:
        return

    # ignore messages with links
    if len(re.findall(link_regex, message['content'])) != 0:
        return

    # replace mentions with respective user
    message['content'] = re.sub(mention_regex, get_user_from_mention, message['content'])

    # remove special characters
    message['content'] = re.sub(special_chars_regex, '', message['content'])

    # at most one space between words
    message['content'] = ' '.join(message['content'].split())

    # ensure message length is within min/max
    if len(message['content']) < min_size or len(message['content']) > max_size:
        return

    return message


# returns all messages in the channel
def get_messages(limit=5):
    messages = []
    last_msg = None

    while True:
        data = send_request(f"/channels/979554513021177909/messages?limit=100&before={last_msg}" if last_msg else "/channels/979554513021177909/messages?limit=100", headers={'Authorization': f'Bot {token}'})

        # break out of loop once there are no more messages
        if not data:
            break
        
        for message in data:
            # prepare message for analysis
            message = prepare_message(message)
            if message is not None:
                # add user to users dict
                get_user_by_id(message['author']['id'])

                messages.append(Message(message['content'], message['id'], message['author']['id'], message['timestamp']))

            # stop once message limit has been reached
            if len(messages) >= limit:
                break
        
        # update id of last message
        last_msg = data[-1]['id']
    
    # reverse ordering of messages (oldest messages at start of list and newest messages at end of list)
    messages.reverse()
    
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
                clusters.append(cluster)
                cluster = []
            
            cluster.append(message)
    
    # add last cluster
    if len(cluster) != 0:
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


# sentiment analysis on entities and messages
def sentiment_analysis(messages):
    # sentiment of this user referring to other users (sentiment of other users referring to this user can be derived from this dict)
    entity_sentiments = {}

    # sentiment of each message (user min/max sentiments can be derived from this dict)
    message_sentiments = {}

    # create groups of messages to send through api (1000 characters = 1 unit)
    content = ""


    # finds the message containing the given mention
    def find_message(mention):
        offset = mention.text.begin_offset
        dist = 2  # distance between two messages in the "content" string (each message is separated with 2 characters, ". ")

        for message in messages:
            # if the mention is contained within the current message, return it
            if len(message.content) > offset:
                return message

            # move to next message
            offset -= len(message.content) + dist
    

    # computes entity and message sentiments for content
    def compute_sentiments(content):
        # ensure that content is contained in a single unit (< 1000 characters)
        assert len(content) < 1000

        # create document
        document = {'content': content, 'type_': type_, 'language': language}
        print(document)

        sentiment_response = client.analyze_sentiment(request={'document': document, 'encoding_type': encoding_type})
        print()
        print(sentiment_response)
        print()

        for sentence in sentiment_response.sentences:
            # find message using span of sentence
            sentence_message = find_message(sentence)

            # update message sentiments
            message_sentiments[sentence_message.message_id] = (sentence.sentiment.score, sentence.sentiment.magnitude)
        
        entity_response = client.analyze_entity_sentiment(request={'document': document, 'encoding_type': encoding_type})
        print()
        print(entity_response)
        print()

        for entity in entity_response.entities:
            # find message using span of entity
            for mention in entity.mentions:
                entity_message = find_message(mention)

                # initialize dict value if it doesnt yet exist
                if users[entity_message.user_id] not in entity_sentiments:
                    entity_sentiments[users[entity_message.user_id]] = {}
                
                if entity.name not in entity_sentiments[users[entity_message.user_id]]:
                    entity_sentiments[users[entity_message.user_id]][entity.name] = []
                
                # update entity sentiments
                entity_sentiments[users[entity_message.user_id]][entity.name].append((mention.sentiment.score, mention.sentiment.magnitude))


    for message in messages:
        if len(message.content) + len(content) < 1000:
            # add message to current group if character limit not reached
            content += message.content + ". "
        else:
            # compute unit of messages
            compute_sentiments(content)
            content = ""
    
    # compute last unit of messages
    if len(content) > 0:
        compute_sentiments(content)
        content = ""
    
    return entity_sentiments, message_sentiments


# removes all entity sentiments that refer to non-user entities
def clean_entity_sentiments(entity_sentiments):
    for this_entity in entity_sentiments:
        # remove all non-user entities
        for other_entity in list(entity_sentiments[this_entity]):
            if other_entity not in users.values():
                del entity_sentiments[this_entity][other_entity]
    
    return entity_sentiments


if __name__ == "__main__":
    messages = get_messages(limit=100)
    messages = coref(create_clusters(messages))
    # entity_sentiments, message_sentiments = sentiment(messages)
    # entity_sentiments, message_sentiments = sentiment_analysis(messages)
    entity_sentiments = {'Donuts': {'above': [(0.0, 0.0), (0.0, 0.0)], 'bot.': [(0.0, 0.0)], 'cluster.': [(0.0, 0.0)], 'Donuts Donuts': [(0.0, 0.0)], 'Donuts': [(0.20000000298023224, 0.20000000298023224), (0.0, 0.0), (0.0, 0.0), (-0.30000001192092896, 0.30000001192092896), (0.0, 0.0), (-0.10000000149011612, 0.10000000149011612), (0.0, 0.0)], 'bot': [(0.10000000149011612, 0.10000000149011612)], 'bot work': [(0.0, 0.0)], 'asdasdas': [(0.30000001192092896, 0.30000001192092896)], 'code': [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)], 'program': [(0.0, 0.0)], 'Donuts yo': [(0.10000000149011612, 0.10000000149011612)], 'marbles': [(-0.20000000298023224, 0.20000000298023224)], 'programs': [(0.0, 0.0), (0.10000000149011612, 0.10000000149011612)], 'work': [(0.0, 0.0)], 'asdasd asdasdasd': [(0.10000000149011612, 0.10000000149011612)], 'thats': [(0.0, 0.0)]}}
    message_sentiments = {'979563889333268500': (0.6000000238418579, 0.6000000238418579), '979563897310838874': (0.0, 0.0), '979563906592821288': (-0.4000000059604645, 0.4000000059604645), '979563938301767761': (0.0, 0.0), '979564107281887303': (-0.30000001192092896, 0.30000001192092896), '979748640572706917': (0.0, 0.0), '979748887768203317': (-0.10000000149011612, 0.10000000149011612), '980998312289271808': (0.10000000149011612, 0.10000000149011612), 
'981013220741488670': (-0.6000000238418579, 0.6000000238418579), '981013299523121172': (-0.10000000149011612, 0.10000000149011612), '981013314618417252': (-0.10000000149011612, 0.10000000149011612), '981013326286962698': (-0.30000001192092896, 0.30000001192092896), '981013337531875439': 
(0.0, 0.0), '981013354841780244': (-0.6000000238418579, 0.6000000238418579), '981013361678508062': (0.0, 0.0), '981013367848337488': (0.0, 0.0), '981053190277591080': (-0.699999988079071, 0.699999988079071), '981086160606617630': (-0.20000000298023224, 0.20000000298023224), '981179196959232000': (0.10000000149011612, 0.10000000149011612)}
    
    print()
    print("Entity Sentiments")
    print(entity_sentiments)

    entity_sentiments = clean_entity_sentiments(entity_sentiments)

    print()
    print("Entity Sentiments")
    print(entity_sentiments)

    # print()
    # print("Message Sentiments")
    # print(message_sentiments)