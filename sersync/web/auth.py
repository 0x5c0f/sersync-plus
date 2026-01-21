"""
Basic Auth 认证模块
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import bcrypt
from typing import Dict, Optional
import structlog

logger = structlog.get_logger()

security = HTTPBasic()


class AuthManager:
    """认证管理器"""

    def __init__(self, users: Optional[Dict[str, str]] = None):
        """
        初始化认证管理器

        Args:
            users: 用户字典 {username: password_hash}
        """
        self.users = users or {
            "admin": self._hash_password("admin")  # 默认用户
        }
        logger.info("Auth manager initialized", users=len(self.users))

    @staticmethod
    def _hash_password(password: str) -> str:
        """使用 bcrypt 哈希密码"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False

    def verify_credentials(self, username: str, password: str) -> bool:
        """
        验证用户凭证

        Args:
            username: 用户名
            password: 密码

        Returns:
            是否验证成功
        """
        if username not in self.users:
            return False

        stored_hash = self.users[username]
        return self._verify_password(password, stored_hash)

    def add_user(self, username: str, password: str):
        """
        添加用户

        Args:
            username: 用户名
            password: 密码
        """
        self.users[username] = self._hash_password(password)
        logger.info("User added", username=username)

    def remove_user(self, username: str):
        """
        删除用户

        Args:
            username: 用户名
        """
        if username in self.users:
            del self.users[username]
            logger.info("User removed", username=username)


# 全局认证管理器
auth_manager = AuthManager()


# ========== 认证依赖 ==========

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    获取当前认证用户

    Args:
        credentials: HTTP Basic 凭证

    Returns:
        用户名

    Raises:
        HTTPException: 认证失败
    """
    username = credentials.username
    password = credentials.password

    if not auth_manager.verify_credentials(username, password):
        logger.warning("Authentication failed", username=username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.debug("User authenticated", username=username)
    return username


def get_current_user_optional(
    credentials: Optional[HTTPBasicCredentials] = Depends(security)
) -> Optional[str]:
    """
    获取当前用户（可选，不强制认证）

    Args:
        credentials: HTTP Basic 凭证

    Returns:
        用户名或 None
    """
    if credentials is None:
        return None

    try:
        return get_current_user(credentials)
    except HTTPException:
        return None
