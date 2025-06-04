import json


class Messages(dict):
    def __init__(self, *, messages_filename: str = "bot/messages.json"):
        self._messages_filename = messages_filename

        with open(self._messages_filename) as f:
            self._messages: dict[str, str] = json.load(f)

    def __getitem__(self, key: str) -> str:
        if key in self._messages:
            return self._messages[key]

        raise KeyError(f"Key '{key}' does not exists in messages.")


if __name__ == "__main__":
    m = Messages()
    print(m["cannot_use_bot"])
