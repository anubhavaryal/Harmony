from datetime import datetime, timedelta
from harmony import db
from harmony.helpers import add_user, prepare_message, send_request
from harmony.models import Channel, CorefMessage, Message, MessageCluster, MessageSentiment, User, UserSentiment
from google.cloud import language_v1
import neuralcoref
import re
import spacy

# TODO: commit all db commands (not in loop but at very end so all commands get ran at once for maximum optimialness)

# load nlp
nlp = spacy.load('en_core_web_sm')
neuralcoref.add_to_pipe(nlp, blacklist=False)

# instantiate google client
client = language_v1.LanguageServiceClient()
type_ = language_v1.types.Document.Type.PLAIN_TEXT
language = "en"
encoding_type = language_v1.EncodingType.UTF8

# constants used by create_clusters
MAX_CUM_DIST = timedelta(minutes=10)  # max amount of time between first and last message in the cluster
MAX_DIST = timedelta(minutes=2)  # max amount of time between consecutive messages in the cluster


class Analyzer:
    def __init__(self, channel_id):
        self.channel_id = channel_id

    # starts analyzing the messages
    def start_analysis(self, limit=5):
        # add channel to database
        db.session.add(Channel(id=self.channel_id, running=True, stage=0, progress=0))
        db.session.commit()

        channel = Channel.query.filter_by(id=self.channel_id)

        # store messages
        print("getting messages")
        self.get_messages(limit)
        print("finished getting messages")

        # cluster messages
        print("clustering messages")
        self.create_clusters()
        print("finished clustering messages")

        # coreference resolution
        print("starting coref")
        self.resolve_coreferences()
        print("finished coref")

        # sentiment analysis
        print("starting sentiment")
        self.analyze_sentiments()
        print("finished sentiment")


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

                    db.session.add(Message(id=message['id'], content=message['content'], timestamp=message['timestamp'], channel_id=self.channel_id, user_id=message['author']['id']))
                    num_msgs += 1

                # stop once message limit has been reached
                if num_msgs >= limit:
                    break
            
            # update id of last message
            last_id = data[-1]['id']
        
        db.session.commit()


    # creates message clusters based on time frame to prepare for coreference resolution
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


    # resolves coreferences in message clusters
    def resolve_coreferences(self):
        user_pattern = re.compile(r"^.+ said $")  # pattern matches "username said "

        # get all messages for this channel
        messages = CorefMessage.query.join(MessageCluster, CorefMessage.cluster_id == MessageCluster.id)\
            .join(Message, CorefMessage.message_id == Message.id)\
            .join(User, Message.user_id == User.id)\
            .filter(MessageCluster.channel_id == self.channel_id)\
            .add_columns(MessageCluster.id, User.username)\
            .all()
        
        prev_id = None  # stores id of previous message cluster
        
        # combine all messages in cluster to assist with coreference resolution
        cluster_message = u""

        for (message, cluster_id, username) in messages:
            if prev_id is None:
                prev_id = cluster_id
            elif prev_id != cluster_id:
                # resolve coreferences
                doc = nlp(cluster_message)

                # update coref messages
                coref_contents = [i[:-1] for i in doc._.coref_resolved.split('"') if not user_pattern.match(i)]
                del coref_contents[-1]

                coref_messages = CorefMessage.query.filter_by(cluster_id=prev_id)
                for (i, coref_message) in enumerate(coref_messages):
                    coref_message.content = coref_contents[i]

                # reset variables
                cluster_message = u""
                prev_id = cluster_id

            # prepare message by surrounding in quotes and prepending it with "(username) said"
            content = username  + ' said "' + message.content.replace('"', '\'') + '." '
            cluster_message += content

        # resolve final cluster
        doc = nlp(cluster_message)

        coref_contents = [i[:-1] for i in doc._.coref_resolved.split('"') if not user_pattern.match(i)]
        del coref_contents[-1]

        coref_messages = CorefMessage.query.filter_by(cluster_id=prev_id)
        for (i, coref_message) in enumerate(coref_messages):
            coref_message.content = coref_contents[i]

        db.session.commit()


    # stores result of sentiment analysis
    def analyze_sentiments(self):
        # get all messages for this channel
        messages = CorefMessage.query.join(Message, CorefMessage.message_id == Message.id).filter(Message.channel_id == self.channel_id)

        # finds the message in the database associated with the mention analyzed by the api
        def find_message(mention):
            offset = mention.text.begin_offset
            dist = 2  # distance between two messages in the "content" string (each message is separated with 2 characters, ". ")

            for message in messages:
                # if the mention is contained within the current message, return its id
                if len(message.content) > offset:
                    return message.message_id

                # move to next message
                offset -= len(message.content) + dist  


        # computes user and message sentiments for content
        def compute_sentiments(content):
            # ensure that content is contained in a single unit (one API unit is < 1000 characters)
            assert len(content) < 1000

            # create document
            document = {'content': content, 'type_': type_, 'language': language}

            sentiment_response = client.analyze_sentiment(request={'document': document, 'encoding_type': encoding_type})

            for sentence in sentiment_response.sentences:
                # find message using span of sentence
                message_id = find_message(sentence)

                # add message sentiment to database
                db.session.add(MessageSentiment(score=sentence.sentiment.score, magnitude=sentence.sentiment.magnitude, message_id=message_id))
            
            db.session.commit()
            
            entity_response = client.analyze_entity_sentiment(request={'document': document, 'encoding_type': encoding_type})

            for entity in entity_response.entities:
                print(entity.name)
                # skip entity if not user
                user = User.query.filter_by(username=entity.name).first()
                if user is not None:
                    for mention in entity.mentions:
                        # find message using span of entity
                        message_id = find_message(mention)
                        message_sentiment_id = Message.query.get(message_id).sentiment.id

                        # add user sentiment to database
                        db.session.add(UserSentiment(score=mention.sentiment.score, magnitude=mention.sentiment.magnitude, user_id=user.id, message_sentiment_id=message_sentiment_id))
            
            db.session.commit()
        

        # stores content of document
        content = ""
        
        for message in messages:
            if len(message.content) + len(content) < 1000:
                # add message to current group if character limit not reached
                content += message.content + ". "
            else:
                compute_sentiments(content)
                content = ""

        # compute last unit of messages
        if len(content) > 0:
            compute_sentiments(content)
