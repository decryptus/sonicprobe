# Sonicprobe 0.3.66

Application mail from `helpers.send_email` and batched logs from `QueueSMTPHandler` now include a Date and Message-ID. Other mail producers can apply the same defaults before serializing an `email.message.Message` or `EmailMessage`.

```python
from sonicprobe.libs.mail import ensure_message_headers

# Set From and any application-owned document ID before calling.
ensure_message_headers(message)
```

The helper fills missing headers in place. New dates use UTC. A new message ID uses the sender’s DNS domain when available and Python’s default message ID otherwise. Existing headers retain their values on repeated calls, so an application can keep the same identifier for retries of a document. Apply the helper before signing the message.
