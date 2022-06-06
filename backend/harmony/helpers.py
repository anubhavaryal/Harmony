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
uid = '240833127713472513'
cid = '979554513021177909'

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


# returns the average sentiment score and magnitude for the object user referring to the subject user
def avg_sentiment(object_user_id, subject_user_id, channel_id):
    # get average score and magnitude for UserSentiments that fit the specified criteria
    avg_score, avg_magnitude = UserSentiment.query.join(Message, UserSentiment.message)\
        .filter(Message.channel_id == channel_id)\
        .filter(UserSentiment.object_user_id == object_user_id)\
        .filter(UserSentiment.subject_user_id == subject_user_id)\
        .with_entities(db.func.avg(UserSentiment.score), db.func.avg(UserSentiment.magnitude)).first()

    return avg_score, avg_magnitude