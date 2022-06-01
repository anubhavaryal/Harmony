CREATE TABLE IF NOT EXISTS server(
    server_id TEXT PRIMARY KEY,
    running INTEGER NOT NULL,
    progress REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user(
    user_id TEXT PRIMARY KEY,
    server_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    FOREIGN KEY(server_id) REFERENCES server(server_id)
);

CREATE TABLE IF NOT EXISTS message(
    message_id TEXT PRIMARY KEY,
    server_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(server_id) REFERENCES server(server_id),
    FOREIGN KEY(user_id) REFERENCES user(user_id)
);

CREATE TABLE IF NOT EXISTS user_sentiment(
    user_sentiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    score REAL NOT NULL,
    magnitude REAL NOT NULL,
    FOREIGN KEY(user_id) REFERENCES user(user_id)
);

CREATE TABLE IF NOT EXISTS message_sentiment(
    message_sentiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    score REAL NOT NULL,
    magnitude REAL NOT NULL,
    FOREIGN KEY(message_id) REFERENCES message(message_id)
);