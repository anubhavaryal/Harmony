from harmony import db
from harmony.models import User, Channel, MessageSentiment, Message, UserSentiment
import os
import re
import requests
import time

# TODO: create another class for helper to store channel_id??
# TODO: remove this
from dotenv import load_dotenv
import os
load_dotenv()

# load token from .env
token = os.getenv("DISCORD_TOKEN")


# returns json associated with request to discord api
def send_request(url):
    request = requests.get(f"https://discord.com/api{url}", headers={'Authorization': f'Bot {token}'})

    # if rate limited, wait "retry_after" seconds
    while request.status_code == 429:
        print("Sleeping because of rate limit.")
        time.sleep(float(request.headers["retry-after"]) / 1000)
        request = requests.get(f"https://discord.com/api{url}", headers={'Authorization': f'Bot {token}'})

    
    return request.json()


# adds user to database
def add_user(user_id, channel_id):
    # check if user and channel exist in database
    user = User.query.get(user_id)
    channel = Channel.query.get(channel_id)

    if user is None:
        # add user to database if it doesnt exist
        data = send_request(f"/users/{user_id}")
        user = User(id=user_id, username=data['username'])

        # create relationship between channel and user
        channel = Channel.query.filter_by(id=channel_id).first()
        user.channels.append(channel)

        db.session.add(user)
        db.session.commit()
    elif channel not in user.channels:
        # add channel to user if not yet a part of user
        user.channels.append(channel)
        db.session.commit()


# prepares Discord message object for analysis
def prepare_message(message, channel_id):
    # min and max length of messages
    min_size = 10
    max_size = 50

    # regex to find links in messages (https://daringfireball.net/2010/07/improved_regex_for_matching_urls)
    link_regex = r"(?i)\b((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    mention_regex = r"<@!?(\d+)>"  # regex to find mentions in messages
    code_regex = r"```.+\n.*\n```"  # regex to find code blocks
    special_chars_regex = r"[^A-Za-z0-9\'\" ]+"  # regex to find special characters (not alphanumeric, quotes, or space)

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


    # return username of the mentioned user
    def get_username_from_mention(match):
        add_user(match.group(1), channel_id)  # group(1) contains id of the mentioned user
        return User.query.get(match.group(1)).username


    # replace mentions with respective user
    message['content'] = re.sub(mention_regex, get_username_from_mention, message['content'])

    # remove special characters
    message['content'] = re.sub(special_chars_regex, '', message['content'])

    # at most one space between words
    message['content'] = ' '.join(message['content'].split())

    # ensure message length is within min/max
    if len(message['content']) < min_size or len(message['content']) > max_size:
        return

    return message


# returns messages with the most and least sentiment in the channel
def min_max_sentiments(channel_id):
    # get all message sentiments in channel
    sentiments = MessageSentiment.query.join(Message, MessageSentiment.message).filter(Message.channel_id == channel_id)
    min_sentiment = sentiments.first()
    max_sentiment = min_sentiment

    for sentiment in sentiments:
        # update min/max sentiments based on score
        if min_sentiment.score > sentiment.score:
            min_sentiment = sentiment
        elif max_sentiment.score < sentiment.score:
            max_sentiment = sentiment

    return min_sentiment, max_sentiment


# returns the average sentiment score and magnitude for a user referring to another user
def avg_sentiment(this_user_id, other_user_id, channel_id):
    # get all user sentiments by this_user that refer to the other_user
    user_sentiments = UserSentiment.query.join(User, UserSentiment.user_id == User.id).join(Channel, User.channels).filter(Channel.id == channel_id).filter(UserSentiment.message_sentiment.message.user.id == this_user_id).filter(U)
    user_sentiments = UserSentiment.query.join(Channel, UserSentiment.message_sentiment.message.user.channels).filter(UserSentiment.user_id == other_user_id).filter(UserSentiment.message_sentiment.message.user.id == this_user_id)
    
    for user_sentiment in user_sentiments:
        # average value of sentiments that were said by this_user


        pass

# # returns average score and magnitude in a list of sentiments
# def average_sentiment(user_sentiments):
#     avg_score, avg_magnitude = 0, 0

#     # calculate average score and magnitude
#     for _, (score, magnitude) in user_sentiments.items():
#         avg_score += score
#         avg_magnitude += magnitude
    
#     avg_score /= len(user_sentiments)
#     avg_magnitude /= len(user_sentiments)

#     return avg_score, avg_magnitude


# # inverts the dict so that it shows how the child refers to the parent (instead of showing how parent refers to child)
# def invert_entity_sentiment(entity_sentiment):
#     inverse = {}

#     for entity in entity_sentiment:
#         for other_entity in entity_sentiment[entity]:
#             # add other entity as parent entity and add entity as child entity
#             if other_entity not in inverse:
#                 inverse[other_entity] = {}
#             inverse[other_entity][entity] = {**inverse.get(other_entity, {}), **entity_sentiment[entity][other_entity]}
    
#     return inverse