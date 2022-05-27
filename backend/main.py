import os
from dotenv import load_dotenv
import spacy
import neuralcoref
import requests
import time
import re

load_dotenv()

# nlp = spacy.load('en_core_web_sm')

# # neuralcoref.add_to_pipe(nlp, conv_dict={'Donuts':['person']})
# neuralcoref.add_to_pipe(nlp, blacklist=False)

# doc = nlp(u'')

# print(doc._.has_coref)
# print(doc._.coref_clusters)

# load discord token from .env 
token = os.getenv("DISCORD_TOKEN")

# average sentiment of other users with referring to this user
sentiments = {'Donuts': {'mossy': 0.7, 'Knuck': 0.5}, 'mossy': {'Donuts': 0.3, 'Knuck': 0.6}, 'Knuck': {'Donuts': -0.9, 'mossy': 0.5}}

# each user and the message id of the message with the most sentiment
max_sentiments = {'Donuts': 1792387123, 'mossy': 123871923, 'Knuck': 12731023}

# each user and the message id of the message with the least sentiment
min_sentiments = {'Donuts': 28713941234, 'mossy': 71928347891234, 'Knuck': 18029348912}

# returns all messages in the channel
def get_messages(num=100):
    messages = []
    last_msg = None

    # loop while message limit has not been reached
    while len(messages) < num:
        request = requests.get(f"https://discord.com/api/channels/979554513021177909/messages?limit=2&before={last_msg}" if last_msg else "https://discord.com/api/channels/979554513021177909/messages?limit=2", headers={'Authorization': f'Bot {token}'})

        # if rate limited, wait "retry_after" seconds
        if request.status_code == 429:
            time.sleep(float(request.headers["retry-after"]) / 1000)
            continue
        
        data = request.json()

        # break out of loop once there are no more messages
        if not data:
            break
        
        for message in data:
            # make sure there are no attachments
            if message['attachments']:
                continue

            # make sure message type is 0 (DEFAULT)
            if message['type'] != 0:
                continue

            print(message['content'])
            # print(message)
        
        # update id of last message
        last_msg = data[-1]['id']
    
    return messages


def cluster(text):
    # max amount of time between start message and last message in the cluster
    max_dist = 5

    # max amount of time between consecutive messages in the cluster
    cons_dist = 1

get_messages()

# print(get_messages().json()[0])
# print(get_messages().headers)