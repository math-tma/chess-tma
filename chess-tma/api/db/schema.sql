-- Reference schema — matches api/db/models.py exactly.
-- Not required at runtime (init_models() creates these via SQLAlchemy),
-- kept here for manual inspection / manual migrations if you prefer raw SQL.

CREATE TABLE users (
    telegram_id BIGINT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    coins INT NOT NULL DEFAULT 0,
    rating INT NOT NULL DEFAULT 1200,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tournaments (
    id SERIAL PRIMARY KEY,
    created_by BIGINT NOT NULL REFERENCES users(telegram_id),
    name VARCHAR(255) NOT NULL,
    format VARCHAR(20) NOT NULL DEFAULT 'single_elimination',
    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    invite_token VARCHAR(64) UNIQUE,
    is_paid BOOLEAN NOT NULL DEFAULT FALSE,
    entry_fee NUMERIC(12,2) DEFAULT 0,
    prize_distribution JSONB,
    max_participants INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'registration',
    starts_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE participants (
    id SERIAL PRIMARY KEY,
    tournament_id INT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
    seed INT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending_payment',
    joined_at TIMESTAMPTZ,
    UNIQUE (tournament_id, user_id)
);

CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    tournament_id INT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    confirmed_by BIGINT REFERENCES users(telegram_id),
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE games (
    id SERIAL PRIMARY KEY,
    match_id INT,
    player_white BIGINT NOT NULL REFERENCES users(telegram_id),
    player_black BIGINT NOT NULL REFERENCES users(telegram_id),
    fen TEXT NOT NULL DEFAULT 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    status VARCHAR(20) NOT NULL DEFAULT 'ongoing',
    winner_id BIGINT REFERENCES users(telegram_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE matches (
    id SERIAL PRIMARY KEY,
    tournament_id INT NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    round INT NOT NULL,
    player1_id BIGINT REFERENCES users(telegram_id),
    player2_id BIGINT REFERENCES users(telegram_id),
    game_id INT REFERENCES games(id),
    winner_id BIGINT REFERENCES users(telegram_id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
);

ALTER TABLE games ADD CONSTRAINT fk_games_match FOREIGN KEY (match_id) REFERENCES matches(id);

CREATE TABLE moves (
    id SERIAL PRIMARY KEY,
    game_id INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    move_number INT NOT NULL,
    uci VARCHAR(10) NOT NULL,
    fen_after TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
