# pylint: disable=redefined-outer-name

import tempfile
import os

import pytest

from fun_game.game.database import Database
from fun_game.game.models import MessageStatus


@pytest.fixture
def db_path():
    # Create temporary database file
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db(db_path):
    return Database(db_path)


def test_get_or_create_user(db: Database):
    with db.connect() as conn:
        # Test creation
        user = conn.get_or_create_user(1, "test_user")
        assert user.upstream_id == 1
        assert user.name == "test_user"

        # Test get existing
        user2 = conn.get_or_create_user(1, "updated_name")
        assert user2.id == user.id
        assert user2.name == "updated_name"


def test_get_user(db: Database):
    with db.connect() as conn:
        # Test non-existent user
        assert conn.get_user(999) is None

        # Test existing user
        conn.get_or_create_user(1, "test_user")
        user = conn.get_user(1)
        assert user is not None
        assert user.upstream_id == 1
        assert user.name == "test_user"


def test_get_or_create_item(db: Database):
    with db.connect() as conn:
        # Test creation
        item_id = conn.get_or_create_item("test_item")
        assert item_id > 0

        # Test get existing
        item_id2 = conn.get_or_create_item("test_item")
        assert item_id == item_id2


def test_get_message_context(db: Database):
    with db.connect() as conn:
        # Create test users
        user_a = conn.get_or_create_user(1, "UserA")
        user_b = conn.get_or_create_user(2, "UserB")
        user_c = conn.get_or_create_user(3, "UserC")
        user_d = conn.get_or_create_user(4, "UserD")

        # Create the conversation thread
        _msg1_id = conn.add_message("hello A", user_a.id)
        msg2_id = conn.add_message("hello B", user_b.id)
        _msg3_id = conn.add_message("what's good?", user_b.id)
        _msg4_id = conn.add_message("today is a good day", user_b.id)
        msg5_id = conn.add_message("hey!", user_c.id, reply_to_id=msg2_id)
        _msg6_id = conn.add_message("irrelevant context", user_d.id)

        # Test context retrieval with reply_to specified and size=1
        messages = conn.get_message_context(msg5_id, size=1)

        # Check that we get exactly the expected messages
        message_contents = [m.content for m in messages]
        print(message_contents)
        assert len(message_contents) == 3
        assert "hello A" in message_contents
        assert "hello B" in message_contents
        assert "today is a good day" in message_contents


def test_custom_rules(db: Database):
    with db.connect() as conn:
        user = conn.get_or_create_user(1, "test_user")

        # Test adding rule
        rule = conn.add_custom_rule("test rule", user.id, False)
        assert rule.rule == "test rule"
        assert not rule.secret

        # Test loading rules
        rules = conn.load_custom_rules()
        assert len(rules) == 1
        assert rules[0].rule == "test rule"

        # Test removing rule
        conn.remove_custom_rule(rule.id)
        conn.remove_custom_rule(rule.id)
        assert len(conn.load_custom_rules()) == 0


def test_reactions(db: Database):
    with db.connect() as conn:
        user = conn.get_or_create_user(1, "test_user")
        msg_id = conn.add_message("Test message", user.id)

        # Test adding reaction
        conn.add_reaction(msg_id, user.id, "👍")
        conn.add_reaction(msg_id, user.id, "👍")
        conn.cursor.execute("SELECT * FROM reactions")
        reactions = conn.cursor.fetchall()
        assert len(reactions) == 1

        # Test removing reaction
        conn.remove_reaction(msg_id, user.id, "👍")
        conn.remove_reaction(msg_id, user.id, "👍")
        conn.cursor.execute("SELECT * FROM reactions")
        reactions = conn.cursor.fetchall()
        assert len(reactions) == 0


def test_message_operations(db: Database):
    with db.connect() as conn:
        user = conn.get_or_create_user(1, "test_user")

        # Test adding message
        msg_id = conn.add_message("Test message", user.id, filtered=True)
        message = conn.get_message(msg_id)  # Should not have upstream id yet
        assert message is None

        # Verify initial state after creation
        m1 = conn.cursor.execute(
            "SELECT * FROM messages WHERE id = ?", (msg_id,)
        ).fetchone()
        assert m1["content"] == "Test message"
        assert m1["status"] == MessageStatus.FILTERED.value
        assert m1["upstream_id"] is None

        # Test marking sent
        conn.mark_message_sent(msg_id, 123)
        conn.mark_message_sent(msg_id, 123)
        message = conn.get_message(123)
        assert message is not None
        assert message.upstream_id == 123
        assert message.status == MessageStatus.FILTERED.value

        # Test unfiltering
        conn.unfilter_message(msg_id)
        conn.unfilter_message(msg_id)
        message = conn.get_message(123)
        assert message is not None and message.status == MessageStatus.UNFILTERED.value

        # Test marking irrelevant
        conn.mark_message_irrelevant(msg_id)
        conn.mark_message_irrelevant(msg_id)
        message = conn.get_message(123)
        assert message is not None and message.status == MessageStatus.IRRELEVANT.value

        message = conn.get_message(123)
        assert message is not None
        assert message.content == "Test message"
        assert message.sender_id == user.id
        assert message.upstream_id == 123
        assert message.status == MessageStatus.IRRELEVANT.value

        # Verify non-existent message returns None
        assert conn.get_message(999) is None


def test_game_state(db: Database):
    with db.connect() as conn:
        user = conn.get_or_create_user(1, "test_user")

        # Test updating world state
        conn.update_game_state(
            user.id,
            world_changes={"item1": True, "item2": True},
            inventory_changes={"item3": True},
            trigger_message_id=None,
        )

        # Test loading world state
        world_state = conn.load_world_state()
        assert "item1" in world_state
        assert "item2" in world_state

        # Test loading inventory
        inventory = conn.load_player_inventory(user.id)
        assert "item3" in inventory

        # Test removing items
        conn.update_game_state(
            user.id,
            world_changes={"item1": False},
            inventory_changes={"item3": False},
            trigger_message_id=None,
        )

        world_state = conn.load_world_state()
        assert "item1" not in world_state
        assert "item2" in world_state
        inventory = conn.load_player_inventory(user.id)
        assert "item3" not in inventory


def test_database_general_exception(db: Database):
    with pytest.raises(Exception):
        with db.connect():
            raise RuntimeError("Test exception")
