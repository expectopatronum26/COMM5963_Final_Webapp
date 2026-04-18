from decimal import Decimal
from types import SimpleNamespace

from models import Post, db
from posts import routes


def _create_post(index, intro_text=""):
    post = Post(
        user_id=1,
        title=f"测试房源{index}",
        rent=Decimal("3000.00") + index,
        location="旺角",
        nearby_school="HKU",
        layout="2室1厅",
        poster_intro=intro_text,
    )
    db.session.add(post)
    return post


def test_chat_api_success(client, app, monkeypatch):
    with app.app_context():
        _create_post(1)
        db.session.commit()

    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="推荐这套 /posts/1"))]
            )

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(routes, "OpenAI", FakeOpenAI)

    response = client.post("/api/chat", json={"message": "我想找3000左右两室"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["answer"] == "推荐这套 /posts/1"
    assert payload["answer_html"] == '<p>推荐这套 <a href="/posts/1">点击查看帖子详情</a></p>'
    assert captured["messages"][1]["role"] == "user"
    assert "/posts/1" in captured["messages"][1]["content"]


def test_chat_api_empty_message_returns_400(client):
    response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_chat_api_provider_failure_returns_502(client, app, monkeypatch):
    with app.app_context():
        _create_post(2)
        db.session.commit()

    class ErrorCompletions:
        def create(self, **kwargs):
            raise RuntimeError("provider unavailable")

    class ErrorChat:
        def __init__(self):
            self.completions = ErrorCompletions()

    class ErrorOpenAI:
        def __init__(self, **kwargs):
            self.chat = ErrorChat()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(routes, "OpenAI", ErrorOpenAI)

    response = client.post("/api/chat", json={"message": "帮我推荐"})

    assert response.status_code == 502
    assert "error" in response.get_json()


def test_chat_api_context_is_truncated_when_budget_exceeded(client, app, monkeypatch):
    with app.app_context():
        _create_post(1, intro_text="A" * 220)
        _create_post(2, intro_text="B" * 220)
        _create_post(3, intro_text="C" * 220)
        db.session.commit()

    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["user_prompt"] = kwargs["messages"][1]["content"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = FakeChat()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(routes, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(routes, "MAX_CONTEXT_CHARS", 320)

    response = client.post("/api/chat", json={"message": "预算3000"})

    assert response.status_code == 200
    assert "已省略" in captured["user_prompt"]

