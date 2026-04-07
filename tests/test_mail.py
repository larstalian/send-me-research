from email.message import EmailMessage

from send_me_research.mail import Mailer


def test_mailer_sends_one_message_per_recipient() -> None:
    sent_messages: list[EmailMessage] = []

    class FakeMailer(Mailer):
        def _send(self, message: EmailMessage) -> None:
            sent_messages.append(message)

    mailer = FakeMailer(
        host="smtp.example.com",
        port=465,
        username="user",
        password="pass",
        sender="sender@example.com",
    )

    mailer.send_text(
        recipients=["one@example.com", "two@example.com"],
        subject="Digest",
        body="hello",
    )

    assert len(sent_messages) == 2
    assert sent_messages[0]["To"] == "one@example.com"
    assert sent_messages[1]["To"] == "two@example.com"
