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
    
    def __eq__(self, other):
        return hasattr(other, 'message_id') and self.message_id == other.message_id

    def __hash__(self):
        return hash(self.message_id)

    def __repr__(self):
        return f"Message('{self.content}', '{self.message_id}', '{self.user_id}', '{self.timestamp}')"
    
    def __str__(self):
        return self.__repr__();


# load discord token from .env 
load_dotenv()
token = os.getenv("DISCORD_TOKEN")

# load nlp
nlp = spacy.load('en_core_web_sm')
neuralcoref.add_to_pipe(nlp, blacklist=False)

# instantiate google client
client = language_v1.LanguageServiceClient()
type_ = language_v1.types.Document.Type.PLAIN_TEXT
language = "en"
encoding_type = language_v1.EncodingType.UTF8

# dict of users for their respective user_id's
users = {'240833127713472513': 'Donuts'}


# returns json associated with request to discord api
def send_request(url):
    request = requests.get(f"https://discord.com/api{url}", headers={'Authorization': f'Bot {token}'})

    # if rate limited, wait "retry_after" seconds
    while request.status_code == 429:
        print("Sleeping because of rate limit.")
        time.sleep(float(request.headers["retry-after"]) / 1000)
        request = requests.get(f"https://discord.com/api{url}", headers={'Authorization': f'Bot {token}'})

    
    return request.json()


# find and returns user with the given id
def get_user_by_id(user_id):
    # if the user has been cached
    if user_id in users:
        return users[user_id]
    
    # find and cache user
    data = send_request(f"/users/{user_id}")
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
        data = send_request(f"/channels/979554513021177909/messages?limit=100{f'&before={last_msg}' if last_msg else ''}")

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
def resolve_coreferences(clusters):
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
    
    original_messages = [message for cluster in clusters for message in cluster]  # flatten cluster
    return messages, original_messages


# sentiment analysis on entities and messages
def analyze_sentiments(messages, original_messages):
    print("DOING SENTIMENT ANALYSIS")
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

        for (message, original_message) in zip(messages, original_messages):
            # if the mention is contained within the current message, return it
            if len(message.content) > offset:
                return original_message

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

            # initialize dict value if it doesnt yet exist
            if users[sentence_message.user_id] not in message_sentiments:
                message_sentiments[users[sentence_message.user_id]] = {}

            # update message sentiments
            message_sentiments[users[sentence_message.user_id]][sentence_message] = (sentence.sentiment.score, sentence.sentiment.magnitude)
        
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
                    entity_sentiments[users[entity_message.user_id]][entity.name] = {}
                
                # update entity sentiments
                entity_sentiments[users[entity_message.user_id]][entity.name][entity_message] = (mention.sentiment.score, mention.sentiment.magnitude)


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


# returns messages with the min/max sentiment
def polarized_sentiments(user_sentiments):
    min_sentiment = None
    max_sentiment = None

    for message in user_sentiments:
        sentiment = (message, *user_sentiments[message])
        
        # if min/max sentiments do not yet have a value
        if min_sentiment is None:
            min_sentiment = sentiment
            max_sentiment = sentiment
        else:
            # update min/max sentiments
            if min_sentiment[1] * min_sentiment[2] > sentiment[1] * sentiment[2]:
                min_sentiment = sentiment
            elif max_sentiment[1] * max_sentiment[2] < sentiment[1] * sentiment[2]:
                max_sentiment = sentiment
    
    return min_sentiment, max_sentiment


# returns average score and magnitude in a list of sentiments
def average_sentiment(user_sentiments):
    avg_score, avg_magnitude = 0, 0

    # calculate average score and magnitude
    for message in user_sentiments:
        avg_score += user_sentiments[message][0]
        avg_magnitude += user_sentiments[message][1]
    
    avg_score /= len(user_sentiments)
    avg_magnitude /= len(user_sentiments)

    return avg_score, avg_magnitude


# inverses the dict so that it shows how the child refers to the parent (instead of showing how parent refers to child)
def invert_entity_sentiment(entity_sentiment):
    inverse = {}
    for entity in entity_sentiment:
        for other_entity in entity_sentiment[entity]:
            if other_entity not in inverse:
                inverse[other_entity] = {}
            inverse[other_entity][entity] = {**inverse.get(other_entity, {}), **entity_sentiment[entity][other_entity]}
    
    return inverse
   

if __name__ == "__main__":
    # messages = get_messages(limit=100)
    # messages, original_messages = resolve_coreferences(create_clusters(messages))
    # entity_sentiments, message_sentiments = analyze_sentiments(messages, original_messages)
    # entity_sentiments, message_sentiments = analyze_sentiments(*resolve_coreferences(create_clusters(get_messages(limit=100))))
    entity_sentiments = {'Donuts': {'above': {Message('the above is a file', '979748887768203317', '240833127713472513', '2022-05-27T14:12:17.698000+00:00'): (0.0, 0.0)}, 'bot.': {Message('testing out the bot', '979563906592821288', '240833127713472513', '2022-05-27T01:57:14.749000+00:00'): (0.0, 0.0)}, 'cluster.': {Message('yo Donuts this should be another cluster', '981013220741488670', '240833127713472513', '2022-05-31T01:56:18.169000+00:00'): (0.0, 0.0)}, 'Donuts Donuts': {Message('yo Donuts this should be another cluster', '981013220741488670', '240833127713472513', '2022-05-31T01:56:18.169000+00:00'): (0.0, 0.0)}, 'Donuts': {Message('but its pretty mudh asdasdas', '979563938301767761', '240833127713472513', '2022-05-27T01:57:22.309000+00:00'): (0.20000000298023224, 0.20000000298023224), Message('i said i was gonna', '981086160606617630', '240833127713472513', '2022-05-31T06:46:08.388000+00:00'): (0.0, 0.0), Message('i am going to lose my marbles', '981053190277591080', '240833127713472513', '2022-05-31T04:35:07.649000+00:00'): (-0.10000000149011612, 0.10000000149011612), Message('yo Donuts this should be another cluster', '981013220741488670', '240833127713472513', '2022-05-31T01:56:18.169000+00:00'): (0.0, 0.0), Message('then they have code', '981013367848337488', '240833127713472513', '2022-05-31T01:56:53.242000+00:00'): (0.0, 0.0)}, 'bot': {Message('and making sure it works', '979563917107920906', '240833127713472513', '2022-05-27T01:57:17.256000+00:00'): (0.10000000149011612, 0.10000000149011612)}, 'bot work': {Message('does this bot work or not', '979564107281887303', '240833127713472513', '2022-05-27T01:58:02.597000+00:00'): (0.0, 0.0)}, 'asdasdas': {Message('but its pretty mudh asdasdas', '979563938301767761', '240833127713472513', '2022-05-27T01:57:22.309000+00:00'): (0.30000001192092896, 0.30000001192092896)}, 'code': {Message('which is just cause there was no code', '981013288622104588', '240833127713472513', '2022-05-31T01:56:34.353000+00:00'): (0.0, 0.0), Message('then you write code', '981013361678508062', '240833127713472513', '2022-05-31T01:56:51.771000+00:00'): (0.0, 0.0), Message('then they have code', '981013367848337488', '240833127713472513', '2022-05-31T01:56:53.242000+00:00'): (0.0, 0.0), Message('programs start with no code', '981013354841780244', '240833127713472513', '2022-05-31T01:56:50.141000+00:00'): (0.0, 0.0)}, 'program': {Message('when the program was just made', '981013314618417252', '240833127713472513', '2022-05-31T01:56:40.551000+00:00'): (0.0, 0.0)}, 'Donuts yo': {Message('Donuts yo whats up', '979748640572706917', '240833127713472513', '2022-05-27T14:11:18.762000+00:00'): (0.10000000149011612, 0.10000000149011612)}, 'marbles': {Message('i am going to lose my marbles', '981053190277591080', '240833127713472513', '2022-05-31T04:35:07.649000+00:00'): (-0.20000000298023224, 0.20000000298023224)}, 'programs': {Message('programs start with no code', '981013354841780244', '240833127713472513', '2022-05-31T01:56:50.141000+00:00'): (0.0, 0.0), Message('programs work', '981013337531875439', '240833127713472513', '2022-05-31T01:56:46.014000+00:00'): (0.10000000149011612, 0.10000000149011612)}, 'work': {Message('cause thats how prgoirams work', '981013326286962698', '240833127713472513', '2022-05-31T01:56:43.333000+00:00'): (0.0, 0.0)}, 'asdasd asdasdasd': {Message('asdasd asdasdasd a', '981179196959232000', '240833127713472513', '2022-05-31T12:55:49.983000+00:00'): (0.10000000149011612, 0.10000000149011612)}, 'thats': {Message('cause thats how prgoirams work', '981013326286962698', '240833127713472513', '2022-05-31T01:56:43.333000+00:00'): (0.0, 0.0)}}}
    message_sentiments = {'Donuts': {Message('whats poppin', '979563889333268500', '240833127713472513', '2022-05-27T01:57:10.634000+00:00'): (0.6000000238418579, 0.6000000238418579), Message('i just got here', '979563897310838874', '240833127713472513', '2022-05-27T01:57:12.536000+00:00'): (0.0, 0.0), Message('testing out the bot', '979563906592821288', '240833127713472513', '2022-05-27T01:57:14.749000+00:00'): (-0.4000000059604645, 0.4000000059604645), Message('but its pretty mudh asdasdas', '979563938301767761', '240833127713472513', '2022-05-27T01:57:22.309000+00:00'): (0.0, 0.0), Message('does this bot work or not', '979564107281887303', '240833127713472513', '2022-05-27T01:58:02.597000+00:00'): (-0.30000001192092896, 0.30000001192092896), Message('Donuts yo whats up', '979748640572706917', '240833127713472513', '2022-05-27T14:11:18.762000+00:00'): (0.0, 0.0), Message('the above is a file', '979748887768203317', '240833127713472513', '2022-05-27T14:12:17.698000+00:00'): (-0.10000000149011612, 0.10000000149011612), Message('pog whats up', '980998312289271808', '240833127713472513', '2022-05-31T00:57:03.717000+00:00'): (0.10000000149011612, 0.10000000149011612), Message('yo Donuts this should be another cluster', '981013220741488670', '240833127713472513', '2022-05-31T01:56:18.169000+00:00'): (-0.6000000238418579, 0.6000000238418579), Message('back then', '981013299523121172', '240833127713472513', '2022-05-31T01:56:36.952000+00:00'): (-0.10000000149011612, 0.10000000149011612), Message('when the program was just made', '981013314618417252', '240833127713472513', '2022-05-31T01:56:40.551000+00:00'): (-0.10000000149011612, 0.10000000149011612), Message('cause thats how prgoirams work', '981013326286962698', '240833127713472513', '2022-05-31T01:56:43.333000+00:00'): (-0.30000001192092896, 0.30000001192092896), Message('programs work', '981013337531875439', '240833127713472513', '2022-05-31T01:56:46.014000+00:00'): (0.0, 0.0), Message('programs start with no code', '981013354841780244', '240833127713472513', '2022-05-31T01:56:50.141000+00:00'): (-0.6000000238418579, 0.6000000238418579), Message('then you write code', '981013361678508062', '240833127713472513', '2022-05-31T01:56:51.771000+00:00'): (0.0, 0.0), Message('then they have code', '981013367848337488', '240833127713472513', '2022-05-31T01:56:53.242000+00:00'): (0.0, 0.0), Message('i am going to lose my marbles', '981053190277591080', '240833127713472513', '2022-05-31T04:35:07.649000+00:00'): (-0.699999988079071, 0.699999988079071), Message('i said i was gonna', '981086160606617630', '240833127713472513', '2022-05-31T06:46:08.388000+00:00'): (-0.20000000298023224, 0.20000000298023224), Message('asdasd asdasdasd a', '981179196959232000', '240833127713472513', '2022-05-31T12:55:49.983000+00:00'): (0.10000000149011612, 0.10000000149011612)}}

    entity_sentiments = clean_entity_sentiments(entity_sentiments)

    # print()
    # print("Entity Sentiments")
    # print(entity_sentiments)

    # print()
    # print("Message Sentiments")
    # print(message_sentiments)

    # avg_score, avg_magnitude = average_sentiment(entity_sentiments['Donuts']['Donuts'])
    # print(avg_score, avg_magnitude)

    print(entity_sentiments)
    print()
    print()
    print(invert_entity_sentiment(entity_sentiments))

    # min_sentiments, max_sentiments = polarized_sentiments(entity_sentiments['Donuts']['Donuts'])
    # print("Most Negative Sentiment", min_sentiments)
    # print()
    # print("Most Positive Sentiment", max_sentiments)
    # print()
    # min_sentiments, max_sentiments = polarized_sentiments(message_sentiments['Donuts'])
    # print("Most Negative Sentiment", min_sentiments)
    # print()
    # print("Most Positive Sentiment", max_sentiments)