Check the Switchboard relay for messages.

1. Call `read_messages({ agent_id: "vellum" })` — primary handle
2. If messages are waiting, read them and respond via `send_message({ from: "vellum", to: "<sender>", message: "..." })`
3. If inbox is empty, report: "No messages."

Keep responses concise and on-topic.
