import sqlite3
from contextlib import contextmanager
from typing import Generator, Optional
import time

from .models import CustomRule, Message, MessageStatus, SimpleMessage, User


class DatabaseConnection:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.cursor = conn.cursor()

    def get_or_create_user(self, upstream_id: int, display_name: str) -> User:
        self.cursor.execute(
            """
            INSERT INTO users (username, upstream_id)
            VALUES (?, ?, ?)
            ON CONFLICT(upstream_id)
            DO UPDATE SET username = excluded.username
            RETURNING id
            """,
            (display_name, upstream_id),
        )
        user_id = self.cursor.fetchone()["id"]
        return User(id=user_id, upstream_id=upstream_id, name=display_name)

    def get_user(self, upstream_id: int) -> Optional[User]:
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

    def get_or_create_item(self, item_name: str) -> int:
        self.cursor.execute(
            "INSERT OR IGNORE INTO items (name) VALUES (?)", (item_name,)
        )
        self.cursor.execute("SELECT id FROM items WHERE name = ?", (item_name,))
        return self.cursor.fetchone()["id"]

    def get_message_context(
        self,
        reply_to: Optional[int],
        size: int = 10,
    ) -> list[SimpleMessage]:
        """
        Returns messages that are contextual to the present one.

        Args:
            user_id: The ID of the user who sent the message
            reply_to: The id of the message being replied to, if any. `size` and `duration` start from here.
            size: The number of messages to return, inclusive of the reply_to message, if provided.
            max_age: The maximum duration in seconds from now/reply_to message for which messages will be included
        """
        seen_messages = set()
        messages = []

        def fetch_context(msg_id: Optional[int], remaining_size: int):
            if not remaining_size:
                return

            status_condition = f"""(
                m.status IS NULL OR
                (m.status != '{MessageStatus.IRRELEVANT.value}'
                 AND m.status != '{MessageStatus.FILTERED.value}'))"""

            if msg_id is None:
                # Fetch recent messages
                query = f"""
                    SELECT m.id, u.username as sender, u.id as sender_id, m.content, m.reply_to_id
                    FROM messages m
                    JOIN users u ON m.sender_id = u.id
                    WHERE {status_condition}
                    ORDER BY m.created_at DESC
                    LIMIT ?
                """
                self.cursor.execute(query, (remaining_size,))
            else:
                # Fetch messages before and including the specified message
                query = f"""
                    SELECT m.id, u.username as sender, u.id as sender_id, m.content, m.reply_to_id
                    FROM messages m
                    JOIN users u ON m.sender_id = u.id
                    WHERE {status_condition} AND m.id <= ?
                    ORDER BY m.created_at DESC
                    LIMIT ?
                """
                self.cursor.execute(query, (msg_id, remaining_size))

            rows = self.cursor.fetchall()
            for row in rows:
                if row["id"] not in seen_messages:
                    seen_messages.add(row["id"])
                    messages.append(
                        SimpleMessage(
                            id=row["id"],
                            sender=row["sender"],
                            sender_id=row["sender_id"],
                            content=row["content"],
                        )
                    )

                    # Recursively fetch context for replied messages
                    if row["reply_to_id"] and row["reply_to_id"] not in seen_messages:
                        fetch_context(row["reply_to_id"], size)

        # Start fetching context
        fetch_context(reply_to, size)

        # Sort messages chronologically
        messages.sort(key=lambda m: m.id)

        return messages

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
            "INSERT INTO custom_rules (rule, creator, secret) VALUES (?, ?, ?)",
            (rule, creator_id, secret),
        )
        return CustomRule(id=self.cursor.fetchone()["id"], rule=rule, secret=secret)

    def remove_custom_rule(self, rule_id: int):
        self.cursor.execute(
            "UPDATE custom_rules SET removed = 0 WHERE id = ?", (rule_id,)
        )

    def add_reaction(self, message_id: int, user_id: Optional[int], reaction: str):
        self.cursor.execute(
            "INSERT INTO reactions (message_id, user_id, reaction) VALUES (?, ?, ?)",
            (message_id, user_id, reaction),
        )

    def remove_reaction(self, message_id: int, user_id: int, reaction: str):
        self.cursor.execute(
            "DELETE FROM reactions WHERE message_id = ? AND user_id = ? AND reaction = ?",
            (message_id, user_id, reaction),
        )

    def add_message(
        self,
        content: str,
        sender_id: int,
        upstream_id: Optional[int] = None,
        reply_to_id: Optional[int] = None,
        filtered: Optional[bool] = False,
    ) -> int:
        self.cursor.execute(
            """INSERT INTO messages (content, sender_id, upstream_id, reply_to_id, status)
               VALUES (?, ?, ?, ?, ?)""",
            (
                content,
                sender_id,
                upstream_id,
                reply_to_id,
                MessageStatus.FILTERED.value if filtered else None,
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

    def get_message(self, upstream_id: int) -> Optional[Message]:
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
        world_changes: Optional[dict[str, bool]],
        inventory_changes: Optional[dict[str, bool]],
        trigger_message_id: Optional[int],  # pylint: disable=unused-argument
    ):
        # XXX: this should probably be version controlled and associated with a particular request id

        # Handle world state changes
        if world_changes:
            for item_name, should_add in world_changes.items():
                item_id = self.get_or_create_item(item_name)
                if should_add:
                    self.cursor.execute(
                        "INSERT OR IGNORE INTO world_state (item_id) VALUES (?)",
                        (item_id,),
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
                        "INSERT OR IGNORE INTO player_inventories (user_id, item_id) VALUES (?, ?)",
                        (user_id, item_id),
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
        """
        )
        return {row["name"] for row in self.cursor.fetchall()}

    def load_player_inventory(self, user_id: int) -> set[str]:
        self.cursor.execute(
            """
            SELECT i.name
            FROM player_inventories pi
            JOIN items i ON pi.item_id = i.id
            WHERE pi.user_id = ?
        """,
            (user_id,),
        )
        return {row["name"] for row in self.cursor.fetchall()}


# pylint: disable=too-few-public-methods
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        self.version = self._get_version()
        self._migrate()

    def _get_version(self) -> int:
        with self.connect() as db:
            db.cursor.execute("SELECT version FROM schema_version")
            return db.cursor.fetchone()["version"]

    def _migrate(self):
        pass

    @contextmanager
    def connect(
        self, max_retries: int = 5, retry_delay: float = 0.1
    ) -> Generator[DatabaseConnection, None, None]:
        conn = None
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                db_conn = DatabaseConnection(conn)
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

                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);

                CREATE TABLE IF NOT EXISTS world_state (
                    item_id INTEGER PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_id) REFERENCES items (id)
                );

                CREATE TABLE IF NOT EXISTS player_inventories (
                    user_id INTEGER,
                    item_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, item_id),
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (item_id) REFERENCES items (id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upstream_id TEXT,
                    sender_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    reply_to_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    FOREIGN KEY (sender_id) REFERENCES users(id),
                    FOREIGN KEY (reply_to_id) REFERENCES messages(id)
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

                CREATE TABLE IF NOT EXISTS custom_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule TEXT NOT NULL,
                    creator INTEGER NOT NULL,
                    secret INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    removed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (creator) REFERENCES users(id)
                )
                CREATE INDEX idx_custom_rules_active ON custom_rules (removed) WHERE removed = 0;
                """
            )
