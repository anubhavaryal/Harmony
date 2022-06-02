from harmony import app

# if the app is currently running
running = False


@app.route("/start")
def start_analysis():
    global running
    running = True
    return "started analysis"


@app.route("/stop")
def stop_analysis():
    global running
    running = False
    return "stopped analysis"


@app.route("/pog")
def pog():
    return str(running)


@app.route("/sentiment/message")
def load_message_sentiments():
    return "a bunch of message sentiments"


@app.route("/sentiment/message/user")
def load_message_sentiments_for_user():
    return "a bunch of message sentiments for specific user"


@app.route("/sentiment/entity")
def load_entity_sentiments():
    return "a bunch of entity sentiments"


@app.route("/sentiment/entity/user")
def load_entity_sentiments_for_user():
    return "a bunch of entity sentiments for specific user"


@app.route("/sentiment/entity/inverse")
def load_entity_sentiments_inverse():
    return "a bunch of entity sentiments but inverted"


@app.route("/sentiment/message/user/polarized")
def load_min_max_message_sentiments():
    return "the minimum and maximum sentiment message for user"