from harmony import db


# bridge entity used for many-many relationship between channels and users
user_bridge_association = db.Table('users',
    db.Column('user_id', db.String(32), db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
    db.Column('channel_id', db.String(32), db.ForeignKey('channel.id', ondelete='CASCADE'), primary_key=True)
)


# each Discord channel being analyzed
class Channel(db.Model):
    id = db.Column(db.String(32), primary_key=True)

    running = db.Column(db.Boolean, nullable=False)  # whether the channel is currently being analyzed
    stage = db.Column(db.Integer, nullable=False)  # the current analysis stage
    progress = db.Column(db.Integer, nullable=False)  # the progress in the current stage
    limit = db.Column(db.Integer, nullable=False)  # max number of messages to analyze

    users = db.relationship('User', secondary=user_bridge_association, back_populates='channels', lazy='dynamic', cascade='all, delete')
    messages = db.relationship('Message', back_populates='channel', cascade='all, delete', passive_deletes=True)
    clusters = db.relationship('MessageCluster', back_populates='channel', cascade='all, delete', passive_deletes=True)
    user_alternates = db.relationship('UserAlternate', back_populates='channel', lazy='dynamic', cascade='all, delete', passive_deletes=True)


# a Discord user
class User(db.Model):
    id = db.Column(db.String(32), primary_key=True)

    username = db.Column(db.String(32), nullable=False)

    channels = db.relationship('Channel', secondary=user_bridge_association, back_populates='users', passive_deletes=True)
    messages = db.relationship('Message', back_populates='user', cascade='all, delete', passive_deletes=True)
    object_sentiments = db.relationship('UserSentiment', foreign_keys='UserSentiment.object_user_id', back_populates='object_user', cascade='all, delete', passive_deletes=True)
    subject_sentiments = db.relationship('UserSentiment', foreign_keys='UserSentiment.subject_user_id', back_populates='subject_user', cascade='all, delete', passive_deletes=True)
    alternates = db.relationship('UserAlternate', back_populates='user', cascade='all, delete', passive_deletes=True)


# an alternate name for the user
class UserAlternate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.String(32), db.ForeignKey('channel.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.String(32), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)

    name = db.Column(db.Text, nullable=False)  # alternate name

    channel = db.relationship('Channel', back_populates='user_alternates')
    user = db.relationship('User', back_populates='alternates')

    def to_json(self):
        return {
            'user_id': self.user_id,
            'name': self.name
        }


# a group of messages that share the same channel and were sent around the same time frame
class MessageCluster(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.String(32), db.ForeignKey('channel.id', ondelete='CASCADE'), nullable=False)

    channel = db.relationship('Channel', back_populates='clusters')
    messages = db.relationship('ClusterMessage', back_populates='cluster', cascade='all, delete', passive_deletes=True)


# a Discord message
class Message(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    channel_id = db.Column(db.String(32), db.ForeignKey('channel.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.String(32), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)

    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Text, nullable=False)

    channel = db.relationship('Channel', back_populates='messages')
    user = db.relationship('User', back_populates='messages')
    cluster_message = db.relationship('ClusterMessage', back_populates='message', uselist=False, cascade='all, delete', passive_deletes=True)
    message_sentiment = db.relationship('MessageSentiment', back_populates='message', uselist=False, cascade='all, delete', passive_deletes=True)
    user_sentiments = db.relationship('UserSentiment', back_populates='message', cascade='all, delete', passive_deletes=True)


# a message that belongs to a cluster
class ClusterMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey('message.id', ondelete='CASCADE'), nullable=False)
    message_cluster_id = db.Column(db.Integer, db.ForeignKey('message_cluster.id', ondelete='CASCADE'), nullable=False)

    message = db.relationship('Message', back_populates='cluster_message')
    coref_message = db.relationship('CorefMessage', back_populates='cluster_message', uselist=False, cascade='all, delete', passive_deletes=True)
    cluster = db.relationship('MessageCluster', back_populates='messages')


# a message after it has had its coreferences resolved
class CorefMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cluster_message_id = db.Column(db.Integer, db.ForeignKey('cluster_message.id', ondelete='CASCADE'), nullable=False)

    content = db.Column(db.Text, nullable=False)  # content of the message after coreference resolution

    cluster_message = db.relationship('ClusterMessage', back_populates='coref_message')
    message = db.relationship('Message', secondary='cluster_message', primaryjoin='CorefMessage.cluster_message_id == ClusterMessage.id', secondaryjoin='ClusterMessage.message_id == Message.id',
        backref=db.backref('coref_message', uselist=False), uselist=False, viewonly=True)


# the sentiment of a message
class MessageSentiment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey('message.id', ondelete='CASCADE'), nullable=False)

    score = db.Column(db.Float, nullable=False)
    magnitude = db.Column(db.Float, nullable=False)

    message = db.relationship('Message', back_populates='message_sentiment')


# the sentiment of the users present in the message contents
class UserSentiment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(32), db.ForeignKey('message.id', ondelete='CASCADE'), nullable=False)
    object_user_id = db.Column(db.String(32), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    subject_user_id = db.Column(db.String(32), db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)

    score = db.Column(db.Float, nullable=False)
    magnitude = db.Column(db.Float, nullable=False)

    message = db.relationship('Message', back_populates='user_sentiments')
    object_user = db.relationship('User', foreign_keys=[object_user_id], back_populates='object_sentiments')  # the user referring to subject_user
    subject_user = db.relationship('User', foreign_keys=[subject_user_id], back_populates='subject_sentiments')  # the user being referred to