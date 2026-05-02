from typing import Any, Protocol

from digest.models import Feedback, PostedMessage


# Protocol は構造的部分型。継承不要で、同名メソッドが揃えば実装とみなされる。
class Notifier(Protocol):
    """配信バックエンドの境界。実装の差し替えはこの Protocol を満たすことだけが条件。"""

    # Protocol のメソッドは本体を持たず ... で型情報のみ宣言する
    def send(self, blocks: list[dict[str, Any]], *, text: str) -> PostedMessage: ...

    def collect_feedback(self, message_id: str) -> list[Feedback]: ...
