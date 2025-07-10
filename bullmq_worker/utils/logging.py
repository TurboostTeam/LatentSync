# 配置日志
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("consumer.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
