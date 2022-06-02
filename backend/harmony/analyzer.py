from datetime import datetime, timedelta
from harmony import db
from harmony.helpers import add_user, prepare_message, send_request
from harmony.models import Channel, CorefMessage, Message, MessageCluster, MessageSentiment, User, UserSentiment
from google.cloud import language_v1
import neuralcoref
import spacy

# TODO: commit all db commands (not in loop but at very end so all commands get ran at once for maximum optimialness)

# load nlp
# nlp = spacy.load('en_core_web_sm')
# neuralcoref.add_to_pipe(nlp, blacklist=False)

# # instantiate google client
# client = language_v1.LanguageServiceClient()
# type_ = language_v1.types.Document.Type.PLAIN_TEXT
# language = "en"
# encoding_type = language_v1.EncodingType.UTF8

# constants used by create_clusters
MAX_CUM_DIST = timedelta(minutes=10)  # max amount of time between first and last message in the cluster
MAX_DIST = timedelta(minutes=2)  # max amount of time between consecutive messages in the cluster


class Analyzer:
    def __init__(self, channel_id):
        self.channel_id = channel_id

    # starts analyzing the messages
    def start_analysis(self, limit=5):
        # add channel to database
        channel = Channel(id=self.channel_id, running=True, stage=0, progress=0)
        db.session.add(channel)

        # store messages
        print("getting messages")
        self.get_messages(limit)
        print("finished getting messages")

        # cluster messages
        print("clustering messages")
        self.create_clusters()
        print("finished clustering messages")


    # stores all messages in the channel in the database
    def get_messages(self, limit):
        last_id = None  # stores id of the last gotten message
        num_msgs = 0  # number of messages gotten

        while True:
            data = send_request(f"/channels/{self.channel_id}/messages?limit=100{f'&before={last_id}' if last_id else ''}")

            # break out of loop once there are no more messages
            if not data:
                break
            
            for message in data:
                # prepare message for analysis
                message = prepare_message(message)
                if message is not None:
                    # store user and message in database
                    add_user(message['author']['id'], self.channel_id)

                    db.session.add(Message(id=message['id'], content=message['content'], timestamp=message['timestamp'], user_id=message['author']['id']))
                    num_msgs += 1

                # stop once message limit has been reached
                if num_msgs >= limit:
                    break
            
            # update id of last message
            last_id = data[-1]['id']
        
        db.session.commit()


    # creates clusters of messages based on time frame to prepare for coreference resolution
    def create_clusters(self):
        first_time = None  # time of first message in the cluster
        last_time = None  # time of last message in the cluster
        cluster_size = 0  # size of current cluster

        # create first cluster 
        cluster = MessageCluster(channel_id=self.channel_id)
        db.session.add(cluster)
        db.session.flush()
        db.session.refresh(cluster)  # refresh so cluster.id is available

        cluster_id = cluster.id  # id of current cluster
        
        for message in Message.query.filter_by():
            message_time = datetime.fromisoformat(message.timestamp)

            if cluster_size == 0:
                # update times
                first_time = last_time = message_time
            else:
                # find time difference between message and first/last cluster messages
                first_delta = first_time - message_time
                last_delta = last_time - message_time

                # if time difference too large/surpasses max dists, create new cluster
                if last_delta > MAX_DIST or first_delta > MAX_CUM_DIST:
                    # create new cluster 
                    cluster = MessageCluster(channel_id=self.channel_id)
                    db.session.add(cluster)
                    db.session.flush()
                    db.session.refresh(cluster)  # refresh so cluster.id is available

                    cluster_id = cluster.id
                    cluster_size = 0

                    # reset time
                    first_time = message_time
                
                last_time = message_time

            # add message to cluster 
            db.session.add(CorefMessage(content=message.content, message_id=message.id, cluster_id=cluster_id))
            cluster_size += 1
        
        db.session.commit()


    # # resolves coreferences in message clusters
    # def resolve_coreferences(clusters):
    #     # messages after updated with coreference resolution
    #     messages = []

    #     # pattern matches "username said "
    #     user_pattern = re.compile(r"^.+ said $")

    #     for cluster in clusters:
    #         # combine all messages in cluster to assist with coreference resolution
    #         cluster_message = u""

    #         for message in cluster:
    #             # prepare message
    #             content = users[message.user_id]  + ' said "' + message.content.replace('"', '\'') + '." '
    #             cluster_message += content
            
    #         # resolve coreferences
    #         doc = nlp(cluster_message)

    #         # dissolve cluster message
    #         new_messages = [i[:-1] for i in doc._.coref_resolved.split('"') if not user_pattern.match(i)]
    #         del new_messages[-1]

    #         for (message, new_message) in zip(cluster, new_messages):
    #             messages.append(Message(new_message, message.message_id, message.user_id, message.timestamp))
        
    #     # original messages passed to function
    #     original_messages = [message for cluster in clusters for message in cluster]  # flatten cluster
    #     return messages, original_messages


    # # sentiment analysis on entities and messages
    # def analyze_sentiments(messages, original_messages):
    #     print("DOING SENTIMENT ANALYSIS")
    #     # sentiment of this user referring to other users (sentiment of other users referring to this user can be derived from this dict)
    #     entity_sentiments = {}

    #     # sentiment of each message (user min/max sentiments can be derived from this dict)
    #     message_sentiments = {}

    #     # stores content of document
    #     content = ""


    #     # finds the message containing the given mention
    #     def find_message(mention):
    #         offset = mention.text.begin_offset
    #         dist = 2  # distance between two messages in the "content" string (each message is separated with 2 characters, ". ")

    #         for (message, original_message) in zip(messages, original_messages):
    #             # if the mention is contained within the current message, return it
    #             if len(message.content) > offset:
    #                 return original_message

    #             # move to next message
    #             offset -= len(message.content) + dist
        

    #     # computes entity and message sentiments for content
    #     def compute_sentiments(content):
    #         # ensure that content is contained in a single unit (one API unit is < 1000 characters)
    #         assert len(content) < 1000

    #         # create document
    #         document = {'content': content, 'type_': type_, 'language': language}

    #         sentiment_response = client.analyze_sentiment(request={'document': document, 'encoding_type': encoding_type})

    #         for sentence in sentiment_response.sentences:
    #             # find message using span of sentence
    #             sentence_message = find_message(sentence)

    #             # initialize dict value if it doesnt yet exist
    #             if users[sentence_message.user_id] not in message_sentiments:
    #                 message_sentiments[users[sentence_message.user_id]] = {}

    #             # update message sentiments
    #             message_sentiments[users[sentence_message.user_id]][sentence_message] = (sentence.sentiment.score, sentence.sentiment.magnitude)
            
    #         entity_response = client.analyze_entity_sentiment(request={'document': document, 'encoding_type': encoding_type})

    #         for entity in entity_response.entities:
    #             # find message using span of entity
    #             for mention in entity.mentions:
    #                 entity_message = find_message(mention)

    #                 # initialize dict value if it doesnt yet exist
    #                 if users[entity_message.user_id] not in entity_sentiments:
    #                     entity_sentiments[users[entity_message.user_id]] = {}
                    
    #                 if entity.name not in entity_sentiments[users[entity_message.user_id]]:
    #                     entity_sentiments[users[entity_message.user_id]][entity.name] = {}
                    
    #                 # update entity sentiments
    #                 entity_sentiments[users[entity_message.user_id]][entity.name][entity_message] = (mention.sentiment.score, mention.sentiment.magnitude)


    #     for message in messages:
    #         if len(message.content) + len(content) < 1000:
    #             # add message to current group if character limit not reached
    #             content += message.content + ". "
    #         else:
    #             # compute unit of messages
    #             compute_sentiments(content)
    #             content = ""
        
    #     # compute last unit of messages
    #     if len(content) > 0:
    #         compute_sentiments(content)
    #         content = ""
        
    #     return entity_sentiments, message_sentiments
