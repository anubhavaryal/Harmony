from flask import request, jsonify
from harmony import app, db
from harmony.analyzer import Analyzer
from harmony.models import Channel, Message, UserAlternate
from harmony.tasks import start_analysis_task, stop_analysis_task
from jsonschema import validate


# creates channel if it doesnt exist and returns it
def channel(channel_id):
    channel = Channel.query.get(channel_id)
    if channel is None:
        # add channel to database
        channel = Channel(id=channel_id, running=False, stage=0, progress=0, limit=0)
        db.session.add(channel)
        db.session.commit()
    
    return channel


# schema to validate /api/channel/<channel_id>/alts POST and DELETE jsons
alt_schema = {
    "type": "array",
    "items": {
        "user_id": {"type": "string"},
        "names": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}


@app.route('/api/channel/<channel_id>/start', methods=['PUT'])
def start(channel_id):
    start_analysis_task.delay(channel_id)
    return '', 202


@app.route('/api/channel/<channel_id>/stop', methods=['PUT'])
def stop(channel_id):
    stop_analysis_task.delay(channel_id)
    return '', 202


# sets the current stage of the channel to stage
@app.route('/api/channel/<channel_id>/stage', methods=['GET', 'PUT'])
def stage(channel_id):
    if request.method == 'PUT':
        stage = request.form.get('stage', type=int)

        # ensure stage is valid
        if 0 > stage > 6:
            return 'Stage must be between 0 and 6', 422
        
        # update stage
        channel(channel_id).stage = stage
        db.session.commit()

        return ''
    else:
        return {'stage': channel(channel_id).stage}


# sets the max message limit for analysis
@app.route('/api/channel/<channel_id>/limit', methods=['GET', 'PUT'])
def limit(channel_id):
    if request.method == 'PUT':
        limit = request.json['limit']
        if limit is None:
            # ensure limit exists
            return 'Did not specify limit', 400
        elif limit <= 0:
            # ensure limit is positive
            return 'Limit must be greater than 0', 422
        
        # update limit
        channel(channel_id).limit = limit
        db.session.commit()
        
        return ''
    else:
        return {"limit": channel(channel_id).limit}


# specifies the user alternates
@app.route('/api/channel/<channel_id>/alts', methods=['GET', 'DELETE', 'POST'])
def alts(channel_id):
    if request.method == 'POST':
        alts = request.json
        validate(instance=alts, schema=alt_schema)

        # add all alternates in json to database
        for alt in alts:
            for name in alt['names']:
                db.session.add(UserAlternate(channel_id=channel_id, user_id=alt['user_id'], name=name))
        
        db.session.commit()
        return ''
    elif request.method == 'DELETE':
        alts = request.json
        validate(instance=alts, schema=alt_schema)

        # remove all alternates in json from database
        for alt in alts:
            for name in alt['names']:
                channel(channel_id).user_alternates.filter(UserAlternate.user_id == alt['user_id']).filter(UserAlternate.name == name).delete()
        
        db.session.commit()
        return ''
    else:
        alts = {}

        # populate dictionary with all alts
        for user_alt in channel(channel_id).user_alternates:
            alt_json = user_alt.to_json()
            alts[alt_json['user_id']] = alts.get(alt_json['user_id'], []) + [alt_json['name']]

        return alts


# returns the progress
@app.route('/api/channel/<channel_id>/pog', methods=['GET'])
def progress(channel_id):
    return {'progress': channel(channel_id).progress}


@app.route('/api/channel/<channel_id>/messages', methods=['GET'])
def messages(channel_id):
    offset = request.args.get('offset', default=0, type=int)
    limit = request.args.get('limit', default=100, type=int)

    return f"{offset} {limit} {channel_id}"

# # if the app is currently running
# running = False


# @app.route("/start")
# def start_analysis():
#     global running
#     running = True
#     return "started analysis"


# @app.route("/stop")
# def stop_analysis():
#     global running
#     running = False
#     return "stopped analysis"


# @app.route("/pog")
# def pog():
#     return str(running)


# @app.route("/sentiment/message")
# def load_message_sentiments():
#     return "a bunch of message sentiments"


# @app.route("/sentiment/message/user")
# def load_message_sentiments_for_user():
#     return "a bunch of message sentiments for specific user"


# @app.route("/sentiment/entity")
# def load_entity_sentiments():
#     return "a bunch of entity sentiments"


# @app.route("/sentiment/entity/user")
# def load_entity_sentiments_for_user():
#     return "a bunch of entity sentiments for specific user"


# @app.route("/sentiment/entity/inverse")
# def load_entity_sentiments_inverse():
#     return "a bunch of entity sentiments but inverted"


# @app.route("/sentiment/message/user/polarized")
# def load_min_max_message_sentiments():
#     return "the minimum and maximum sentiment message for user"