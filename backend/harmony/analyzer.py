from datetime import datetime, timedelta
from harmony import db
from harmony.helpers import add_user, prepare_message, send_request
from harmony.models import Channel, CorefMessage, ClusterMessage, Message, MessageCluster, MessageSentiment, User, UserSentiment
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
                message = prepare_message(message, self.channel_id)
                if message is not None:
                    # store user and message in database
                    add_user(message['author']['id'], self.channel_id)

                    db.session.add(Message(id=message['id'], channel_id=self.channel_id, user_id=message['author']['id'], content=message['content'], timestamp=message['timestamp']))
                    num_msgs += 1

                    # stop once message limit has been reached
                    if num_msgs >= limit:
                        break
            
            # update id of last message
            last_id = data[-1]['id']
        
        db.session.commit()

    # creates message clusters based on time frame to prepare for coreference resolution
    def create_clusters(self):
        # get all messages
        messages = Channel.query.get(self.channel_id).messages
        messages_to_add = []  # messages that are going to be added to the current cluster

        # add all messages in messages_to_add to cluster
        def add_cluster():
            nonlocal messages_to_add

            # find id for this cluster
            cluster = MessageCluster(channel_id=self.channel_id)
            db.session.add(cluster)
            db.session.flush()
            db.session.refresh(cluster)  # refresh so cluster.id is available

            # add all messages to cluster
            for message_to_add in messages_to_add:
                db.session.add(ClusterMessage(message_id=message_to_add.id, message_cluster_id=cluster.id))
            
            messages_to_add = []

        # store times of first and last message in cluster
        first_time = datetime.fromisoformat(messages[0].timestamp)
        last_time = first_time

        for message in messages:
            message_time = datetime.fromisoformat(message.timestamp)

            # check if message is not within the bounds of the current cluster
            if first_time - message_time > MAX_CUM_DIST or last_time - message_time > MAX_DIST:
                add_cluster()
                first_time = message_time
            
            messages_to_add.append(message)
            last_time = message_time
        
        # add last cluster
        if len(messages_to_add) > 0:
            add_cluster()
        
        db.session.commit()

    # resolves coreferences in message clusters
    def resolve_coreferences(self):
        user_pattern = re.compile(r"^.+ said $")  # pattern matches "username said "

        # get all clusters for this channel
        clusters = Channel.query.get(self.channel_id).clusters
        for cluster in clusters:
            # combine all messages in cluster to assist with coreference resolution
            combined_message = u""

            for message in cluster.messages:
                # prepare message by surrounding in quotes and prepending it with "(username) said"
                combined_message += message.message.user.username  + ' said "' + message.message.content.replace('"', '\'') + '." '

            # resolve coreferences
            doc = nlp(combined_message)

            # dissolve combined message
            coref_contents = [i[:-1] for i in doc._.coref_resolved.split('"') if not user_pattern.match(i)]
            del coref_contents[-1]

            # create coref messages
            for (i, message) in enumerate(cluster.messages):
                db.session.add(CorefMessage(cluster_message_id=message.id, content=coref_contents[i]))
        
        db.session.commit()

    # stores result of sentiment analysis
    def analyze_sentiments(self):
        # get all messages for this channel
        messages = CorefMessage.query.join(Message, CorefMessage.message).filter(Message.channel_id == self.channel_id)

        # finds the message in the database associated with the mention analyzed by the api
        def find_message(mention):
            offset = mention.text.begin_offset
            dist = 2  # distance between two messages in the "content" string (each message is separated with 2 characters, ". ")

            for message in messages:
                # if the mention is contained within the current message, return its id
                if len(message.content) > offset:
                    return message.message.id

                # move to next message
                offset -= len(message.content) + dist

        # computes user and message sentiments for content
        def compute_sentiments(content):
            print("COMPUTING SENTIMNENTS")
            # ensure that content is contained in a single unit (one API unit is < 1000 characters)
            assert len(content) < 1000

            # create document
            document = {'content': content, 'type_': type_, 'language': language}

            # calculate message sentiments
            sentiment_response = client.analyze_sentiment(request={'document': document, 'encoding_type': encoding_type})
            for sentence in sentiment_response.sentences:
                # find message using span of sentence
                message_id = find_message(sentence)

                # add message sentiment to database
                db.session.add(MessageSentiment(message_id=message_id, score=sentence.sentiment.score, magnitude=sentence.sentiment.magnitude))
            
            # calculate user sentiments
            entity_response = client.analyze_entity_sentiment(request={'document': document, 'encoding_type': encoding_type})
            for entity in entity_response.entities:
                print("entity name:", entity.name)
                # skip entity if not user
                subject_user = Channel.query.get(self.channel_id).users.filter(User.username == entity.name).first()
                if subject_user is not None:
                    for mention in entity.mentions:
                        # find message using span of entity
                        message_id = find_message(mention)
                        object_user = Message.query.get(message_id).user

                        # add user sentiment to database
                        db.session.add(UserSentiment(message_id=message_id, object_user_id=object_user.id, subject_user_id=subject_user.id, score=mention.sentiment.score, magnitude=mention.sentiment.magnitude))
            
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
