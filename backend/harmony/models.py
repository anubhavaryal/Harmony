from harmony import db


# bridge entity used for many-many relationship between channels and users
user_bridge_association = db.Table('users',
    db.Column('user_id', db.String(32), db.ForeignKey('user.id'), primary_key=True),
    db.Column('channel_id', db.String(32), db.ForeignKey('channel.id'), primary_key=True)
)


# each Discord channel being analyzed
class Channel(db.Model):
    id = db.Column(db.String(32), primary_key=True)

    running = db.Column(db.Boolean, nullable=False)  # whether the channel is currently being analyzed
    stage = db.Column(db.Integer, nullable=False)  # the current analysis stage
    progress = db.Column(db.Integer, nullable=False)  # the progress in the current stage

    users = db.relationship('User', secondary=user_bridge_association, back_populates='channels', lazy='dynamic')
    messages = db.relationship('Message', back_populates='channel')
    clusters = db.relationship('MessageCluster', back_populates='channel')


# a Discord user
class User(db.Model):
    id = db.Column(db.String(32), primary_key=True)

    username = db.Column(db.String(32), nullable=False)

    channels = db.relationship('Channel', secondary=user_bridge_association, back_populates='users')
    messages = db.relationship('Message', back_populates='user')
    object_sentiments = db.relationship('UserSentiment', foreign_keys='UserSentiment.object_user_id', back_populates='object_user')
    subject_sentiments = db.relationship('UserSentiment', foreign_keys='UserSentiment.subject_user_id', back_populates='subject_user')


# a group of messages that share the same channel and were sent around the same time frame
class MessageCluster(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.String(32), db.ForeignKey('channel.id'), nullable=False)

    channel = db.relationship('Channel', back_populates='clusters')
    messages = db.relationship('ClusterMessage', back_populates='cluster')


# a Discord message
class Message(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    channel_id = db.Column(db.String(32), db.ForeignKey('channel.id'), nullable=False)
    user_id = db.Column(db.String(32), db.ForeignKey('user.id'), nullable=False)

    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Text, nullable=False)

    channel = db.relationship('Channel', back_populates='messages')
    user = db.relationship('User', back_populates='messages')
    cluster_message = db.relationship('ClusterMessage', back_populates='message', uselist=False)
    message_sentiment = db.relationship('MessageSentiment', back_populates='message', uselist=False)
    user_sentiments = db.relationship('UserSentiment', back_populates='message')


# a message that belongs to a cluster
class ClusterMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey('message.id'), nullable=False)
    message_cluster_id = db.Column(db.Integer, db.ForeignKey('message_cluster.id'), nullable=False)

    message = db.relationship('Message', back_populates='cluster_message')
    coref_message = db.relationship('CorefMessage', back_populates='cluster_message', uselist=False)
    cluster = db.relationship('MessageCluster', back_populates='messages')


# a message after it has had its coreferences resolved
class CorefMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cluster_message_id = db.Column(db.Integer, db.ForeignKey('cluster_message.id'), nullable=False)

    content = db.Column(db.Text, nullable=False)  # content of the message after coreference resolution

    cluster_message = db.relationship('ClusterMessage', back_populates='coref_message')
    message = db.relationship('Message', secondary='cluster_message', primaryjoin='CorefMessage.cluster_message_id == ClusterMessage.id', secondaryjoin='ClusterMessage.message_id == Message.id',
        backref=db.backref('coref_message', uselist=False), uselist=False, viewonly=True)


# the sentiment of a message
class MessageSentiment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey('message.id'), nullable=False)

    score = db.Column(db.Float, nullable=False)
    magnitude = db.Column(db.Float, nullable=False)

    message = db.relationship('Message', back_populates='message_sentiment')


# the sentiment of the users present in the message contents
class UserSentiment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey('message.id'), nullable=False)
    object_user_id = db.Column(db.String(32), db.ForeignKey('user.id'), nullable=False)
    subject_user_id = db.Column(db.String(32), db.ForeignKey('user.id'), nullable=False)

    score = db.Column(db.Float, nullable=False)
    magnitude = db.Column(db.Float, nullable=False)

    message = db.relationship('Message', back_populates='user_sentiments')
    object_user = db.relationship('User', foreign_keys=[object_user_id], back_populates='object_sentiments')  # the user referring to subject_user
    subject_user = db.relationship('User', foreign_keys=[subject_user_id], back_populates='subject_sentiments')  # the user being referred to