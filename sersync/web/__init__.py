"""
Sersync Web 管理界面

功能:
- FastAPI Web 服务
- WebSocket 实时推送
- REST API 接口
- 基础认证
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import List, Dict, Any
import structlog
from pathlib import Path

from sersync.web.auth import get_current_user

logger = structlog.get_logger()


# ========== WebSocket 连接管理器 ==========

class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """连接 WebSocket 客户端"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        """断开 WebSocket 客户端"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected", total=len(self.active_connections))

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """发送消息给指定客户端"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error("Failed to send message", error=str(e))

    async def broadcast(self, message: dict):
        """广播消息给所有客户端"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("Failed to broadcast", error=str(e))
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        return len(self.active_connections)


# 全局连接管理器
manager = ConnectionManager()


# ========== 广播函数（供引擎调用）==========

async def broadcast_to_clients(message: dict):
    """
    广播消息到所有 WebSocket 客户端

    Args:
        message: 消息字典
    """
    await manager.broadcast(message)


# ========== FastAPI 应用 ==========

def create_app(enable_auth: bool = True) -> FastAPI:
    """
    创建 FastAPI 应用

    Args:
        enable_auth: 是否启用认证

    Returns:
        FastAPI 应用实例
    """
    app = FastAPI(
        title="Sersync Web API",
        description="Sersync 文件同步系统 Web 管理界面",
        version="0.1.0"
    )

    # 挂载静态文件
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # 注册路由
    from sersync.web.routes import status, config, logs, control, sync_history

    app.include_router(status.router, prefix="/api/status", tags=["status"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
    app.include_router(sync_history.router, prefix="/api/sync-history", tags=["sync-history"])

    # 控制路由需要认证
    if enable_auth:
        app.include_router(control.router, prefix="/api/control", tags=["control"])
    else:
        # 无认证模式（开发环境）
        from fastapi import APIRouter
        no_auth_router = APIRouter()

        @no_auth_router.post("/start")
        async def start_engine():
            return await control.start_engine(current_user="admin")

        @no_auth_router.post("/stop")
        async def stop_engine():
            return await control.stop_engine(current_user="admin")

        @no_auth_router.post("/full-sync")
        async def trigger_full_sync():
            return await control.trigger_full_sync(current_user="admin")

        @no_auth_router.post("/clear-fail-log")
        async def clear_fail_log():
            return await control.clear_fail_log(current_user="admin")

        app.include_router(no_auth_router, prefix="/api/control", tags=["control"])

    # WebSocket 端点
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket 连接端点"""
        await manager.connect(websocket)
        try:
            while True:
                # 保持连接，接收客户端消息（如果有）
                data = await websocket.receive_text()
                # 可以在这里处理客户端发送的消息
                logger.debug("Received from client", data=data)
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception as e:
            logger.error("WebSocket error", error=str(e))
            manager.disconnect(websocket)

    # 首页
    @app.get("/", response_class=HTMLResponse)
    async def read_root():
        """返回首页"""
        index_path = static_path / "index.html"
        if index_path.exists():
            return index_path.read_text()
        else:
            return """
            <html>
                <head><title>Sersync Web</title></head>
                <body>
                    <h1>Sersync Web 管理界面</h1>
                    <p>API 文档: <a href="/docs">/docs</a></p>
                </body>
            </html>
            """

    # 健康检查
    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        return {
            "status": "healthy",
            "service": "sersync-web",
            "websocket_clients": len(manager.active_connections)
        }

    logger.info(
        "FastAPI application created",
        auth_enabled=enable_auth,
        static_path=str(static_path)
    )

    return app


def setup_engine_integration(app: FastAPI):
    """
    设置引擎集成（将 WebSocket 推送连接到引擎）

    Args:
        app: FastAPI 应用实例
    """
    from sersync.core.engine import get_engine_instance

    engine = get_engine_instance()
    if engine:
        # 设置引擎的 Web 推送回调
        engine.set_web_broadcast_callback(broadcast_to_clients)
        logger.info("Engine WebSocket integration configured")
    else:
        logger.warning("No engine instance available for WebSocket integration")


__all__ = [
    'create_app',
    'setup_engine_integration',
    'broadcast_to_clients',
    'manager'
]
