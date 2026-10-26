from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal
from .junction_profile import active_profile
CARLA_IDLE_WATCHDOG_FLAG = Path('/tmp/carla-server-idle-flag')

def require_town10hd(world: Any) -> str:
    expected = active_profile().map_name
    if expected.startswith('Nansha'):
        return expected
    map_name = str(world.get_map().name)
    if expected not in map_name:
        raise RuntimeError(f'当前地图 {map_name} 不是 {expected}；为避免服务端崩溃，客户端不会切图')
    return map_name

def clear_idle_watchdog_flag() -> None:
    CARLA_IDLE_WATCHDOG_FLAG.unlink(missing_ok=True)

class CarlaSession:

    def __init__(self, world: Any, fixed_delta_seconds: float=0.1, client: Any | None=None) -> None:
        if fixed_delta_seconds <= 0:
            raise ValueError('固定步长必须为正数')
        self.world = world
        self.fixed_delta_seconds = fixed_delta_seconds
        self._original_settings: Any | None = None
        self._cleanups: list[Callable[[], None]] = []
        self._actors: list[tuple[Any, bool]] = []
        self._client = client

    def __enter__(self) -> CarlaSession:
        require_town10hd(self.world)
        self._original_settings = self.world.get_settings()
        synchronous = self.world.get_settings()
        synchronous.synchronous_mode = True
        synchronous.fixed_delta_seconds = self.fixed_delta_seconds
        if self.fixed_delta_seconds > 0.1:
            synchronous.substepping = False
        self.world.apply_settings(synchronous)
        return self

    def register_cleanup(self, cleanup: Callable[[], None]) -> None:
        self._cleanups.append(cleanup)

    def register_actor(self, actor: Any, *, stop_before_destroy: bool=False) -> Any:
        self._actors.append((actor, stop_before_destroy))
        return actor

    def _destroy_actors(self) -> list[str]:
        errors: list[str] = []
        for (actor, stop_before_destroy) in self._actors:
            if stop_before_destroy:
                try:
                    actor.stop()
                except BaseException as error:
                    errors.append(f'stop {actor.id}: {error}')
        ids = [actor.id for (actor, _) in self._actors]
        self._actors.clear()
        if not ids:
            return errors
        if self._client is None:
            for actor_id in ids:
                errors.append(f'no client: actor {actor_id} 未 batch 销毁')
            return errors
        import carla
        replies = self._client.apply_batch([carla.command.DestroyActor(i) for i in ids], False) or []
        self._client.apply_batch_sync([], False)
        errors += [str(r.error) for r in replies if r.has_error()]
        return errors

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> Literal[False]:
        cleanup_errors: list[BaseException] = []
        for cleanup in reversed(self._cleanups):
            try:
                cleanup()
            except BaseException as error:
                cleanup_errors.append(error)
        if self._original_settings is not None:
            try:
                self._original_settings.synchronous_mode = False
                self.world.apply_settings(self._original_settings)
            except BaseException as error:
                cleanup_errors.append(error)
        if exc is None and cleanup_errors:
            raise RuntimeError(f'CARLA 资源清理失败: {cleanup_errors[0]}') from cleanup_errors[0]
        return False
