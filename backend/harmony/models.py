from harmony import db

'''
data to store
--------------
- request
    - user cache
        - user id
            - username
        - user id
        - user id
    - running status (true/false)
    - progress status (0.0 - 1.0)
    - entity sentiments
        - entity
            - other entity
                - sentiment
                    - score
                    - magnitude
                - sentiment
                - sentiment
            - another entity
                - ...
    - message sentiments
        - entity
            - message
                - sentiment
                    - score
                    - magnitude
            - message
            - message
'''

users = db.Table('users', 
    db.Column('user_id', db.String(32), db.ForeignKey('user.id'), primary_key=True), 
    db.Column('channel_id', db.String(32), db.ForeignKey('channel.id'), primary_key=True)
)

class Channel(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    running = db.Column(db.Boolean, nullable=False)
    stage = db.Column(db.Integer, nullable=False)
    progress = db.Column(db.Integer, nullable=False)
    users = db.relationship('User', secondary=users, lazy='subquery', backref=db.backref('channels', lazy=True))
    clusters = db.relationship('MessageCluster', backref='channel', lazy=True)
    # messages = db.relationship('Message', backref='channel', lazy=True)

    def __repr__(self):
        return f"Channel('{self.id}', {self.running}, {self.progress})"

class User(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    username = db.Column(db.String(32), nullable=False)
    # channel_id = db.Column(db.String(32), db.ForeignKey('channel.id'), nullable=False)
    messages = db.relationship('Message', backref='user', lazy=True)
    sentiments = db.relationship('UserSentiment', backref='user', lazy=True)

    def __repr__(self):
        return f"User('{self.id}', '{self.username}')"

class Message(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Text, nullable=False)
    # channel_id = db.Column(db.String(32), db.ForeignKey('channel.id'), nullable=False)
    user_id = db.Column(db.String(32), db.ForeignKey('user.id'), nullable=False)
    coref_message = db.relationship('CorefMessage', backref='message', uselist=False)
    sentiments = db.relationship('MessageSentiment', backref='message', lazy=True)

    def __repr__(self):
        return f"Message('{self.id}', '{self.content}', '{self.timestamp}', '{self.user_id}')"

class CorefMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    message_id = db.Column(db.Text, db.ForeignKey('message.id'), nullable=False)
    cluster_id = db.Column(db.Integer, db.ForeignKey('message_cluster.id'), nullable=False)

    def __repr__(self):
        return f"CorefMessage({self.id}, '{self.content}', '{self.message_id}', '{self.cluster_id}')"

class MessageCluster(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coref_messages = db.relationship('CorefMessage', backref='cluster', lazy=True)
    channel_id = db.Column(db.String(32), db.ForeignKey('channel.id'), nullable=False)

    def __repr__(self):
        return f"MessageCluster({self.id}, '{self.channel_id}')"

class UserSentiment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Float, nullable=False)
    magnitude = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.String(32), db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"UserSentiment({self.id}, {self.score}, {self.magnitude}, '{self.user_id}')"

class MessageSentiment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Float, nullable=False)
    magnitude = db.Column(db.Float, nullable=False)
    message_id = db.Column(db.String(32), db.ForeignKey('message.id'), nullable=False)

    def __repr__(self):
        return f"MessageSentiment({self.id}, {self.score}, {self.magnitude}, '{self.message_id}')"
