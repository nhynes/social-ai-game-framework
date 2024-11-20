import sqlite3
from contextlib import contextmanager
from typing import Generator
import time

from .models import Objective, CustomRule, Message, MessageStatus, SimpleMessage, User


class DatabaseConnection:
    def __init__(self, conn: sqlite3.Connection, db: "Database"):
        self.conn = conn
        self.cursor = conn.cursor()
        self.db = db
        self._game_id = db.get_active_game_id()

    def get_or_create_user(self, upstream_id: int, display_name: str) -> User:
        self.cursor.execute(
            """
            INSERT INTO users (username, upstream_id)
            VALUES (?, ?)
            ON CONFLICT(upstream_id)
            DO UPDATE SET username = excluded.username
            RETURNING id
            """,
            (display_name, upstream_id),
        )
        user_id = self.cursor.fetchone()["id"]
        return User(id=user_id, upstream_id=upstream_id, name=display_name)

    def get_user(self, upstream_id: int) -> User | None:
        self.cursor.execute(
            "SELECT * FROM users WHERE upstream_id = ?",
            (upstream_id,),
        )
        row = self.cursor.fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            upstream_id=upstream_id,
            name=row["username"],
        )

    def create_game(self) -> int | None:
        self.cursor.execute("INSERT INTO games DEFAULT VALUES")
        game_id = self.cursor.lastrowid
        if game_id:
            self._game_id = game_id
            self.db.set_active_game_id(game_id)
        return game_id

    def get_last_game_id(self) -> int:
        self.cursor.execute(
            """
            SELECT id FROM games
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return self.cursor.fetchone()[0]

    def get_or_create_item(self, item_name: str) -> int:
        self.cursor.execute(
            "INSERT OR IGNORE INTO items (name) VALUES (?)", (item_name,)
        )
        self.cursor.execute("SELECT id FROM items WHERE name = ?", (item_name,))
        return self.cursor.fetchone()["id"]

    def get_message_context(
        self,
        base_message: int,
        size: int = 10,
    ) -> list[SimpleMessage]:
        """
        Returns messages contextual to the provided base message.
        A contextual message satisfies any of:
            * sent up to `size` messages before the base message
            * a message that was replied to by a message already in the context
            * sent up to `size` messages before a replied-to message
        """
        query = """
            WITH RECURSIVE
            previous_messages AS (
                SELECT m.id, m.sender_id, m.content, u.username as sender
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.id <= :base_msg AND m.game_id =:game_id
                ORDER BY m.id DESC
                LIMIT :size
            ),

            reply_chain AS (
                SELECT m.id, m.sender_id, m.content, m.reply_to_id, u.username as sender
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE (m.id IN (SELECT id FROM previous_messages) OR m.id = :base_msg)
                AND m.game_id = :game_id

                UNION

                SELECT m.id, m.sender_id, m.content, m.reply_to_id, u.username as sender
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                JOIN reply_chain rc ON m.id = rc.reply_to_id
                WHERE m.game_id = :game_id
            ),

            reply_context AS (
                SELECT DISTINCT m.id, m.sender_id, m.content, u.username as sender
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                JOIN reply_chain rc
                WHERE m.id <= rc.id
                AND m.id >= rc.id - :size
                AND m.id NOT IN (SELECT id FROM reply_chain)
                AND m.game_id = :game_id
            ),

            combined_context AS (
                SELECT id, sender_id, sender, content FROM previous_messages
                UNION
                SELECT id, sender_id, sender, content FROM reply_chain
                UNION
                SELECT id, sender_id, sender, content FROM reply_context
            )

            SELECT DISTINCT id, sender, sender_id, content
            FROM combined_context
            WHERE id != :base_msg
            ORDER BY id;
        """

        params = {"game_id": self._game_id, "base_msg": base_message, "size": size}

        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()

        return [
            SimpleMessage(id=row[0], sender=row[1], sender_id=row[2], content=row[3])
            for row in rows
        ]

    def load_custom_rules(self) -> list[CustomRule]:
        self.cursor.execute(
            "SELECT id, rule, secret FROM custom_rules WHERE removed = 0"
        )
        return [
            CustomRule(id=row["id"], rule=row["rule"], secret=bool(row["secret"]))
            for row in self.cursor.fetchall()
        ]

    def add_custom_rule(self, rule: str, creator_id: int, secret: bool) -> CustomRule:
        self.cursor.execute(
            "INSERT INTO custom_rules (rule, creator, secret) VALUES (?, ?, ?) RETURNING id",
            (rule, creator_id, secret),
        )
        return CustomRule(id=self.cursor.fetchone()["id"], rule=rule, secret=secret)

    def remove_custom_rule(self, rule_id: int):
        self.cursor.execute(
            "UPDATE custom_rules SET removed = 1 WHERE id = ?", (rule_id,)
        )

    def load_objectives(self) -> dict[int, list[Objective]]:
        self.cursor.execute(
            """
            SELECT users.upstream_id, objectives.id, objectives.objective_text, objectives.score
            FROM objectives JOIN users ON objectives.user_id = users.id
            WHERE objectives.game_id = ?
            """,
            (self._game_id,)
        )
        objectives: dict[int, list[Objective]] = {}
        for user_upstream_id, objective_id, objective_text, score in self.cursor.fetchall():
            user_upstream_id = int(user_upstream_id)
            if user_upstream_id not in objectives:
                objectives[user_upstream_id] = []
            objectives[user_upstream_id].append(Objective(id=objective_id, objective_text=objective_text, score=score))
        return objectives

    def add_objective(self, objective_text: str, user_id: int) -> Objective:
        self.cursor.execute(
            "INSERT INTO objectives (objective_text, user_id, score, game_id) VALUES (?, ?, ?, ?) RETURNING id",
            (objective_text, user_id, 0, self._game_id),
        )
        return Objective(id=self.cursor.fetchone()["id"], objective_text=objective_text, score=0)

    def add_reaction(self, message_id: int, user_id: int | None, reaction: str):
        self.cursor.execute(
            "INSERT OR IGNORE INTO reactions (message_id, user_id, reaction) VALUES (?, ?, ?)",
            (message_id, user_id, reaction),
        )

    def remove_reaction(self, message_id: int, user_id: int, reaction: str):
        self.cursor.execute(
            "DELETE FROM reactions WHERE user_id = ? AND message_id = ? AND reaction = ?",
            (message_id, user_id, reaction),
        )

    def add_message(
        self,
        content: str,
        sender_id: int,
        upstream_id: int | None = None,
        reply_to_id: int | None = None,
        filtered: bool | None = False,
    ) -> int:
        self.cursor.execute(
            """INSERT INTO messages (content, sender_id, upstream_id, reply_to_id, status, game_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                content,
                sender_id,
                upstream_id,
                reply_to_id,
                MessageStatus.FILTERED.value if filtered else None,
                self._game_id,
            ),
        )
        assert self.cursor.lastrowid
        return self.cursor.lastrowid

    def mark_message_sent(self, message_id: int, upstream_id: int):
        self.cursor.execute(
            "UPDATE messages SET upstream_id = ? WHERE id = ?",
            (upstream_id, message_id),
        )

    def unfilter_message(self, message_id: int):
        self.cursor.execute(
            f"""
            UPDATE messages SET status = '{MessageStatus.UNFILTERED.value}'
            WHERE id = ? AND status = '{MessageStatus.FILTERED.value}'
            """,
            (message_id,),
        )

    def mark_message_irrelevant(self, message_id: int):
        self.cursor.execute(
            "UPDATE messages SET status = 'irrelevant' WHERE id = ?",
            (message_id,),
        )

    def get_message(self, upstream_id: int) -> Message | None:
        self.cursor.execute(
            "SELECT * FROM messages WHERE upstream_id = ?",
            (upstream_id,),
        )
        row = self.cursor.fetchone()
        if not row:
            return None
        return Message(
            id=row["id"],
            upstream_id=upstream_id,
            sender_id=row["sender_id"],
            content=row["content"],
            reply_to=row["reply_to_id"],
            created_at=row["created_at"],
            status=row["status"],
        )

    def update_game_state(
        self,
        user_id: int,
        world_changes: dict[str, bool] | None,
        inventory_changes: dict[str, bool] | None,
        trigger_message_id: int | None,  # pylint: disable=unused-argument
    ):
        # XXX: this should probably be version controlled and associated with a particular request id

        # Handle world state changes
        if world_changes:
            for item_name, should_add in world_changes.items():
                item_id = self.get_or_create_item(item_name)
                if should_add:
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO world_state (item_id, game_id) VALUES (?, ?)",
                        (item_id, self._game_id,),
                    )
                else:
                    self.cursor.execute(
                        "DELETE FROM world_state WHERE item_id = ?", (item_id,)
                    )

        # Handle inventory changes
        if inventory_changes:
            for item_name, should_add in inventory_changes.items():
                item_id = self.get_or_create_item(item_name)
                if should_add:
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO player_inventories (user_id, item_id, game_id) VALUES (?, ?, ?)",
                        (user_id, item_id, self._game_id),
                    )
                else:
                    self.cursor.execute(
                        "DELETE FROM player_inventories WHERE user_id = ? AND item_id = ?",
                        (user_id, item_id),
                    )

    def load_world_state(self) -> set[str]:
        self.cursor.execute(
            """
            SELECT i.name
            FROM world_state ws
            JOIN items i ON ws.item_id = i.id
            WHERE ws.game_id = ?
        """,
        (self._game_id,)
        )
        return {row["name"] for row in self.cursor.fetchall()}

    def load_player_inventory(self, user_id: int) -> set[str]:
        self.cursor.execute(
            """
            SELECT i.name
            FROM player_inventories pi
            JOIN items i ON pi.item_id = i.id
            WHERE pi.user_id = ? AND pi.game_id = ?
        """,
            (user_id, self._game_id,),
        )
        return {row["name"] for row in self.cursor.fetchall()}


# pylint: disable=too-few-public-methods
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._active_game_id = None
        self._init_db()
        with self.connect() as db:
            self._active_game_id = db.get_last_game_id()
        self.version = self._get_version()
        self._migrate()

    def _get_version(self) -> int:
        with self.connect() as db:
            db.cursor.execute("SELECT version FROM schema_version")
            return db.cursor.fetchone()["version"]

    def _migrate(self):
        pass

    def set_active_game_id(self, game_id):
        self._active_game_id = game_id

    def get_active_game_id(self):
        return self._active_game_id

    @contextmanager
    def connect(
        self, max_retries: int = 5, retry_delay: float = 0.1
    ) -> Generator[DatabaseConnection, None, None]:
        conn = None
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                db_conn = DatabaseConnection(conn, self)
                conn.execute("BEGIN TRANSACTION")
                yield db_conn
                conn.commit()
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    if conn:
                        conn.rollback()
                    raise
            except Exception as e:
                if conn:
                    conn.rollback()
                raise e
            finally:
                if conn:
                    conn.close()

    def _init_db(self):
        with self.connect() as db:
            db.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO schema_version VALUES (1);

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    upstream_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_upstream_id ON users(upstream_id);

                INSERT OR IGNORE INTO users (id, username, upstream_id) VALUES (0, 'System', 0);

                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                INSERT OR IGNORE INTO games (id) VALUES (1);

                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

                CREATE TABLE IF NOT EXISTS world_state (
                    item_id INTEGER PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    game_id INTEGER NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES items (id),
                    FOREIGN KEY (game_id) REFERENCES games (id)
                );

                CREATE TABLE IF NOT EXISTS player_inventories (
                    user_id INTEGER,
                    item_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    game_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, item_id),
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (item_id) REFERENCES items (id),
                    FOREIGN KEY (game_id) REFERENCES games (id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upstream_id TEXT,
                    sender_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    reply_to_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    game_id INTEGER NOT NULL,
                    status TEXT,
                    FOREIGN KEY (sender_id) REFERENCES users(id),
                    FOREIGN KEY (reply_to_id) REFERENCES messages(id),
                    FOREIGN KEY (game_id) REFERENCES games (id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_upstream_id ON messages(upstream_id);

                CREATE TABLE IF NOT EXISTS reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    reaction TEXT NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_reactions_unique ON reactions (message_id, user_id, reaction);

                CREATE TABLE IF NOT EXISTS custom_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule TEXT NOT NULL,
                    creator INTEGER NOT NULL,
                    secret INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    removed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (creator) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_custom_rules_active ON custom_rules (removed) WHERE removed = 0;

                CREATE TABLE IF NOT EXISTS objectives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    objective_text TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    game_id INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (game_id) REFERENCES games (id)
                );
                """
            )
