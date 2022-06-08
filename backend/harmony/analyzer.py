import neuralcoref
import re
import spacy
from datetime import datetime, timedelta
from harmony import db
from harmony.helpers import Helper, send_request
from harmony.models import Channel, CorefMessage, ClusterMessage, Message, MessageCluster, MessageSentiment, User, UserAlternate, UserSentiment
from google.cloud import language_v1


# TODO: commit all db commands (not in loop but at very end so all commands get ran at once for maximum optimialness)

# load nlp
nlp = spacy.load('en_core_web_sm')
neuralcoref.add_to_pipe(nlp, blacklist=False)  # disable blacklist to allow "i", "you", etc. to be resolved

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
        self.channel = Channel.query.get(self.channel_id)
        self.helper = Helper(self.channel_id)

    # starts analyzing the messages
    # is idempotent as it does nothing if self.channel.running is True
    def start_analysis(self):
        print("starting analysis")

        # check if channel previously analyzed
        if self.channel is None:
            # add channel to database
            db.session.add(Channel(id=self.channel_id, running=False, stage=0, progress=0, limit=0))
            db.session.commit()

            self.channel = Channel.query.get(self.channel_id)
            self.helper = Helper(self.channel_id)
        elif self.channel.running:
            # do not start another analysis if one is ongoing
            print("channel is already running")
            return
        
        # set running to true so other instances cannot analyze until this instance finishes
        self.channel.running = True
        
        # reset progress
        self.channel.progress = 0
        db.session.commit()

        if self.channel.stage == 0:
            # stage 0: set limit
            pass
        elif self.channel.stage == 1:
            # stage 1: gather messages
            self.channel.users = []  # remove user relationships
            Message.query.filter(Message.channel_id == self.channel_id).delete()  # clear all messages
            db.session.commit()

            self.get_messages()
        elif self.channel.stage == 2:
            # stage 2: establish user alternates
            self.channel.user_alternates.delete()  # clear all user alternates
            db.session.commit()

            pass
        elif self.channel.stage == 3:
            # stage 3: cluster messages
            MessageCluster.query.filter(MessageCluster.channel_id == self.channel_id).delete()  # clear all message clusters
            db.session.commit()

            self.create_clusters()
        elif self.channel.stage == 4:
            # stage 4: coreference resolution
            coref_subquery = CorefMessage.query.join(Message, CorefMessage.message).filter(Message.channel_id == self.channel_id).with_entities(CorefMessage.id).subquery()
            CorefMessage.query.filter(CorefMessage.id.in_(coref_subquery)).delete(synchronize_session=False)  # clear all coref messages
            db.session.commit()

            self.resolve_coreferences()
        elif self.channel.stage == 5:
            # stage 5: sentiment analysis
            msg_sent_subquery = MessageSentiment.query.join(Message, MessageSentiment.message).filter(Message.channel_id == self.channel_id).with_entities(MessageSentiment.id).subquery()
            user_sent_subquery = UserSentiment.query.join(Message, UserSentiment.message).filter(Message.channel_id == self.channel_id).with_entities(UserSentiment.id).subquery()

            MessageSentiment.query.filter(MessageSentiment.id.in_(msg_sent_subquery)).delete(synchronize_session=False)  # clear message sentiments
            UserSentiment.query.filter(UserSentiment.id.in_(user_sent_subquery)).delete(synchronize_session=False)  # clear user sentiments
            db.session.commit()

            self.analyze_sentiments()
        else:
            # stage X: finished
            self.channel.running = False
            db.session.commit()
            return
        
        # move to the next stage if current stage wasnt aborted
        print("about to upgrade stage")
        if self.channel.running:
            print("upgraded stage")
            self.channel.stage = Channel.stage + 1
            self.channel.running = False
            db.session.commit()
    
    # stops analysis (analysis may continue for a short time until a breaking condition is reached)
    # is idempotent
    def stop_analysis(self):
        if self.channel is not None:
            self.channel.running = False

    # # sets the max number of messages to analyze
    # def set_limit(self, limit):
    #     if self.channel is not None and self.channel.stage == 0:
    #         self.channel.limit = limit
    #         self.channel.stage = 1
    #         self.channel.running = False
    #         db.session.commit()

    # stores all messages in the channel in the database
    def get_messages(self):
        last_id = None  # stores id of the last gotten message
        num_msgs = 0  # number of messages gotten
        limit = self.channel.limit  # max number of messages to get

        while True:
            data = send_request(f"/channels/{self.channel_id}/messages?limit=100{f'&before={last_id}' if last_id else ''}")

            # break out of loop once there are no more messages
            if not data:
                break
            
            for message in data:
                # make sure analysis is running
                if not self.channel.running:
                    break
                
                # stop once message limit has been reached
                if num_msgs >= limit:
                    break

                # prepare message for analysis
                message = self.helper.prepare_message(message)
                if message is not None:
                    # store user and message in database
                    self.helper.add_user(message['author']['id'])

                    db.session.add(Message(id=message['id'], channel_id=self.channel_id, user_id=message['author']['id'], content=message['content'], timestamp=message['timestamp']))
                    num_msgs += 1
                    self.channel.progress = num_msgs  # update progress
                    db.session.commit()
            
            # update id of last message
            last_id = data[-1]['id']
        
        db.session.commit()
    
    # # sets alternate names for each user
    # # each alternate is formatted as ("user_id", "alternate name") | (string, string)
    # def set_alternates(self, alternates):
    #     if self.channel.stage != 2:
    #         return
        
    #     for (user_id, alternate_name) in alternates:
    #         # make sure analysis is running
    #         if not self.channel.running:
    #             break

    #         # if the user exists in the channel
    #         if self.channel.users.get(user_id) is not None:
    #             db.session.add(UserAlternate(channel_id=self.channel_id, user_id=user_id, name=alternate_name))
    #             self.channel.progress = Channel.progress + 1  # update progress
        
    #     self.channel.stage = 3
    #     self.channel.running = False
    #     db.session.commit()

    # creates message clusters based on time frame to prepare for coreference resolution
    def create_clusters(self):
        # get all messages
        messages = self.channel.messages
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
            
            self.channel.progress = Channel.progress + 1  # update progress
            messages_to_add = []

        # store times of first and last message in cluster
        first_time = datetime.fromisoformat(messages[0].timestamp)
        last_time = first_time

        for message in messages:
            # make sure analysis is running
            if not self.channel.running:
                break

            message_time = datetime.fromisoformat(message.timestamp)

            # check if message is not within the bounds of the current cluster
            if first_time - message_time > MAX_CUM_DIST or last_time - message_time > MAX_DIST:
                add_cluster()
                first_time = message_time
            
            messages_to_add.append(message)
            last_time = message_time
        
        # add last cluster
        if len(messages_to_add) > 0 and self.channel.running:
            add_cluster()
        
        db.session.commit()

    # resolves coreferences in message clusters
    def resolve_coreferences(self):
        user_pattern = re.compile(r"^.+ said $")  # pattern matches "username said "

        # get all clusters for this channel
        clusters = self.channel.clusters
        for cluster in clusters:
            # make sure analysis is running
            if not self.channel.running:
                break

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
                self.channel.progress = Channel.progress + 1  # update progress
        
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
        
        # returns the user associated with the alternate name
        def find_user_alternate(name):
            user_alternate = self.channel.user_alternates.filter(UserAlternate.name.ilike(name)).first()
            if user_alternate is None:
                return None
            else:
                return user_alternate.user

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
                # skip if user with name or alternate name does not exist
                subject_user = self.channel.users.filter(User.username.ilike(entity.name)).first() or find_user_alternate(entity.name)
                if subject_user is not None:
                    for mention in entity.mentions:
                        # find message using span of entity
                        message_id = find_message(mention)
                        object_user = Message.query.get(message_id).user

                        # add user sentiment to database
                        db.session.add(UserSentiment(message_id=message_id, object_user_id=object_user.id, subject_user_id=subject_user.id, score=mention.sentiment.score, magnitude=mention.sentiment.magnitude))
            
            self.channel.progress = Channel.progress + 1  # update progress
            db.session.commit()
        
        # stores content of document
        content = ""
        
        for message in messages:
            # make sure analysis is running
            if not self.channel.running:
                break

            if len(message.content) + len(content) < 1000:
                # add message to current group if character limit not reached
                content += message.content + ". "
            else:
                compute_sentiments(content)
                content = ""

        # compute last unit of messages
        if len(content) > 0 and self.channel.running:
            compute_sentiments(content)
