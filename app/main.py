"""
TradingAgents-CN v1.0.0-preview FastAPI Backend
娑撹绨查悽銊р柤鎼村繐鍙嗛崣?
Copyright (c) 2025 hsliuping. All rights reserved.
閻楀牊娼堥幍鈧張?(c) 2025 hsliuping閵嗗倷绻氶悾娆愬閺堝娼堥崚鈹库偓?
This software is proprietary and confidential. Unauthorized copying, distribution,
or use of this software, via any medium, is strictly prohibited.
閺堫剝钂嬫禒鏈佃礋娑撴挻婀侀崪灞炬簚鐎靛棜钂嬫禒韬测偓鍌欏紬缁備線鈧俺绻冩禒璁崇秿婵帊绮欓張顏嗙病閹哄牊娼堟径宥呭煑閵嗕礁鍨庨崣鎴炲灗娴ｈ法鏁ら張顒冭拫娴犺翰鈧?
For commercial licensing, please contact: iyocn@sina.com
閸熷棔绗熺拋绋垮讲閸溿劏顕楅敍宀冾嚞閼辨梻閮撮敍姝╯liup@163.com
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import time
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging_config import setup_logging
from app.routers import auth_db as auth, analysis, screening, queue, sse, health, favorites, config, reports, database, operation_logs, tags, tushare_init, akshare_init, baostock_init, historical_data, multi_period_sync, financial_data, news_data, social_media, internal_messages, usage_statistics, model_capabilities, cache, logs
from app.routers import sync as sync_router, multi_source_sync
from app.routers import stocks as stocks_router
from app.routers import stock_data as stock_data_router
from app.routers import stock_sync as stock_sync_router
from app.routers import multi_market_stocks as multi_market_stocks_router
from app.routers import notifications as notifications_router
from app.routers import websocket_notifications as websocket_notifications_router
from app.routers import scheduler as scheduler_router
from app.services.basics_sync_service import get_basics_sync_service
from app.services.multi_source_basics_sync_service import MultiSourceBasicsSyncService
from app.services.scheduler_service import set_scheduler_instance
from app.worker.tushare_sync_service import (
    run_tushare_basic_info_sync,
    run_tushare_quotes_sync,
    run_tushare_historical_sync,
    run_tushare_financial_sync,
    run_tushare_status_check
)
from app.worker.akshare_sync_service import (
    run_akshare_basic_info_sync,
    run_akshare_quotes_sync,
    run_akshare_historical_sync,
    run_akshare_financial_sync,
    run_akshare_status_check
)
from app.worker.baostock_sync_service import (
    run_baostock_basic_info_sync,
    run_baostock_daily_quotes_sync,
    run_baostock_historical_sync,
    run_baostock_status_check
)
# 濞擃垵鍋傞崪宀€绶ㄩ懖鈩冩暭娑撶儤瀵滈棁鈧懢宄板絿+缂傛挸鐡ㄥΟ鈥崇础閿涘奔绗夐崘宥夋付鐟曚礁鐣鹃弮璺烘倱濮濄儰鎹㈤崝?# from app.worker.hk_sync_service import ...
# from app.worker.us_sync_service import ...
from app.middleware.operation_log_middleware import OperationLogMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.services.quotes_ingestion_service import QuotesIngestionService
from app.routers import paper as paper_router


def get_version() -> str:
    """娴?VERSION 閺傚洣娆㈢拠璇插絿閻楀牊婀伴崣?""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return "1.0.0"  # 姒涙顓婚悧鍫熸拱閸?

async def _print_config_summary(logger):
    """閺勫墽銇氶柊宥囩枂閹芥顩?""
    try:
        logger.info("=" * 70)
        logger.info("棣冩惖 TradingAgents-CN Configuration Summary")
        logger.info("=" * 70)

        # .env 閺傚洣娆㈢捄顖氱窞娣団剝浼?        import os
        from pathlib import Path
        
        current_dir = Path.cwd()
        logger.info(f"棣冩惂 Current working directory: {current_dir}")
        
        # 濡偓閺屻儱褰查懗鐣屾畱 .env 閺傚洣娆㈡担宥囩枂
        env_files_to_check = [
            current_dir / ".env",
            current_dir / "app" / ".env",
            Path(__file__).parent.parent / ".env",  # 妞ゅ湱娲伴弽鍦窗瑜?        ]
        
        logger.info("棣冩敵 Checking .env file locations:")
        env_file_found = False
        for env_file in env_files_to_check:
            if env_file.exists():
                logger.info(f"  閴?Found: {env_file} (size: {env_file.stat().st_size} bytes)")
                env_file_found = True
                # 閺勫墽銇氶弬鍥︽閻ㄥ嫬澧犻崙鐘侯攽閿涘牓娈ｉ挊蹇旀櫛閹扮喍淇婇幁顖ょ礆
                try:
                    with open(env_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[:5]  # 閸欘亣顕伴崜?鐞?                        logger.info(f"     Preview (first 5 lines):")
                        for i, line in enumerate(lines, 1):
                            # 闂呮劘妫岄崠鍛儓鐎靛棛鐖滈妴浣哥槕闁姐儳鐡戦弫蹇斿妳娣団剝浼呴惃鍕攽
                            if any(keyword in line.upper() for keyword in ['PASSWORD', 'SECRET', 'KEY', 'TOKEN']):
                                logger.info(f"       {i}: {line.split('=')[0]}=***")
                            else:
                                logger.info(f"       {i}: {line.strip()}")
                except Exception as e:
                    logger.warning(f"     Could not preview file: {e}")
            else:
                logger.info(f"  閴?Not found: {env_file}")
        
        if not env_file_found:
            logger.warning("閳跨媴绗? No .env file found in checked locations")
        
        # Pydantic Settings 闁板秶鐤嗛崝鐘烘祰閻樿埖鈧?        logger.info("閳挎瑱绗? Pydantic Settings Configuration:")
        logger.info(f"  閳?Settings class: {settings.__class__.__name__}")
        logger.info(f"  閳?Config source: {getattr(settings.model_config, 'env_file', 'Not specified')}")
        logger.info(f"  閳?Encoding: {getattr(settings.model_config, 'env_file_encoding', 'Not specified')}")
        
        # 閺勫墽銇氭稉鈧禍娑樺彠闁款噣鍘ょ純顔尖偓鑲╂畱閺夈儲绨敍鍫㈠箚婢у啫褰夐柌?vs 姒涙顓婚崐纭风礆
        key_settings = ['HOST', 'PORT', 'DEBUG', 'MONGODB_HOST', 'REDIS_HOST']
        logger.info("  閳?Key settings sources:")
        for setting_name in key_settings:
            env_var_name = setting_name
            env_value = os.getenv(env_var_name)
            config_value = getattr(settings, setting_name, None)
            if env_value is not None:
                logger.info(f"    - {setting_name}: from environment variable ({config_value})")
            else:
                logger.info(f"    - {setting_name}: using default value ({config_value})")
        
        # 閻滎垰顣ㄦ穱鈩冧紖
        env = "Production" if settings.is_production else "Development"
        logger.info(f"Environment: {env}")

        # 閺佺増宓佹惔鎾圭箾閹?        logger.info(f"MongoDB: {settings.MONGODB_HOST}:{settings.MONGODB_PORT}/{settings.MONGODB_DATABASE}")
        logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")

        # 娴狅絿鎮婇柊宥囩枂
        import os
        if settings.HTTP_PROXY or settings.HTTPS_PROXY:
            logger.info("Proxy Configuration:")
            if settings.HTTP_PROXY:
                logger.info(f"  HTTP_PROXY: {settings.HTTP_PROXY}")
            if settings.HTTPS_PROXY:
                logger.info(f"  HTTPS_PROXY: {settings.HTTPS_PROXY}")
            if settings.NO_PROXY:
                # 閸欘亝妯夌粈鍝勫3娑擃亜鐓欓崥?                no_proxy_list = settings.NO_PROXY.split(',')
                if len(no_proxy_list) <= 3:
                    logger.info(f"  NO_PROXY: {settings.NO_PROXY}")
                else:
                    logger.info(f"  NO_PROXY: {','.join(no_proxy_list[:3])}... ({len(no_proxy_list)} domains)")
            logger.info(f"  閴?Proxy environment variables set successfully")
        else:
            logger.info("Proxy: Not configured (direct connection)")

        # 濡偓閺屻儱銇囧Ο鈥崇€烽柊宥囩枂
        try:
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            if config and config.llm_configs:
                enabled_llms = [llm for llm in config.llm_configs if llm.enabled]
                logger.info(f"Enabled LLMs: {len(enabled_llms)}")
                if enabled_llms:
                    for llm in enabled_llms[:3]:  # 閸欘亝妯夌粈鍝勫3娑?                        logger.info(f"  閳?{llm.provider}: {llm.model_name}")
                    if len(enabled_llms) > 3:
                        logger.info(f"  閳?... and {len(enabled_llms) - 3} more")
                else:
                    logger.warning("閳跨媴绗? No LLM enabled. Please configure at least one LLM in Web UI.")
            else:
                logger.warning("閳跨媴绗? No LLM configured. Please configure at least one LLM in Web UI.")
        except Exception as e:
            logger.warning(f"閳跨媴绗? Failed to check LLM configs: {e}")

        # 濡偓閺屻儲鏆熼幑顔界爱闁板秶鐤?        try:
            if config and config.data_source_configs:
                enabled_sources = [ds for ds in config.data_source_configs if ds.enabled]
                logger.info(f"Enabled Data Sources: {len(enabled_sources)}")
                if enabled_sources:
                    for ds in enabled_sources[:3]:  # 閸欘亝妯夌粈鍝勫3娑?                        logger.info(f"  閳?{ds.type.value}: {ds.name}")
                    if len(enabled_sources) > 3:
                        logger.info(f"  閳?... and {len(enabled_sources) - 3} more")
            else:
                logger.info("Data Sources: Using default (AKShare)")
        except Exception as e:
            logger.warning(f"閳跨媴绗? Failed to check data source configs: {e}")

        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"Failed to print config summary: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """鎼存梻鏁ら悽鐔锋嚒閸涖劍婀＄粻锛勬倞"""
    # 閸氼垰濮╅弮璺哄灥婵瀵?    setup_logging()
    logger = logging.getLogger("app.main")

    # 妤犲矁鐦夐崥顖氬З闁板秶鐤?    try:
        from app.core.startup_validator import validate_startup_config
        validate_startup_config()
    except Exception as e:
        logger.error(f"闁板秶鐤嗘宀冪槈婢惰精瑙? {e}")
        raise

    await init_db()

    #  闁板秶鐤嗗銉﹀复閿涙艾鐨㈢紒鐔剁闁板秶鐤嗛崘娆忓弳閻滎垰顣ㄩ崣姗€鍣洪敍灞肩返 TradingAgents 閺嶇绺炬惔鎾插▏閻?    try:
        from app.core.config_bridge import bridge_config_to_env
        bridge_config_to_env()
    except Exception as e:
        logger.warning(f"閳跨媴绗? 闁板秶鐤嗗銉﹀复婢惰精瑙? {e}")
        logger.warning("閳跨媴绗? TradingAgents 鐏忓棔濞囬悽?.env 閺傚洣娆㈡稉顓犳畱闁板秶鐤?)

    # Apply dynamic settings (log_level, enable_monitoring) from ConfigProvider
    try:
        from app.services.config_provider import provider as config_provider  # local import to avoid early DB init issues
        eff = await config_provider.get_effective_system_settings()
        desired_level = str(eff.get("log_level", "INFO")).upper()
        setup_logging(log_level=desired_level)
        for name in ("webapi", "worker", "uvicorn", "fastapi"):
            logging.getLogger(name).setLevel(desired_level)
        try:
            from app.middleware.operation_log_middleware import set_operation_log_enabled
            set_operation_log_enabled(bool(eff.get("enable_monitoring", True)))
        except Exception:
            pass
    except Exception as e:
        logging.getLogger("webapi").warning(f"Failed to apply dynamic settings: {e}")

    # 閺勫墽銇氶柊宥囩枂閹芥顩?    await _print_config_summary(logger)

    logger.info("TradingAgents FastAPI backend started")

    # 閸氼垰濮╅張鐕傜窗閼汇儵娓剁憰浣告躬娴兼垵绔堕弮鎯八夐崗鍛瑐娑撯偓娴溿倖妲楅弮銉︽暪閻╂ê鎻╅悡?    if settings.QUOTES_BACKFILL_ON_STARTUP:
        try:
            qi = QuotesIngestionService()
            await qi.ensure_indexes()
            await qi.backfill_last_close_snapshot_if_needed()
        except Exception as e:
            logger.warning(f"Startup backfill failed (ignored): {e}")

    # 閸氼垰濮╁В蹇旀）鐎规碍妞傛禒璇插閿涙艾褰查柊宥囩枂
    scheduler: AsyncIOScheduler | None = None
    try:
        from croniter import croniter
    except Exception:
        croniter = None  # 閸欘垶鈧绶风挧?    try:
        scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

        # 娴ｈ法鏁ゆ径姘殶閹诡喗绨崥灞绢劄閺堝秴濮熼敍鍫熸暜閹镐浇鍤滈崝銊ュ瀼閹诡澁绱?        multi_source_service = MultiSourceBasicsSyncService()

        # 閺嶈宓?TUSHARE_ENABLED 闁板秶鐤嗛崘鍐茬暰娴兼ê鍘涢弫鐗堝祦濠?        # 婵″倹鐏?Tushare 鐞氼偆顩﹂悽顭掔礉缁崵绮烘导姘冲殰閸斻劋濞囬悽銊ュ従娴犳牕褰查悽銊︽殶閹诡喗绨敍鍦揔Share/BaoStock閿?        preferred_sources = None  # None 鐞涖劎銇氭担璺ㄦ暏姒涙顓绘导妯哄帥缁狙囥€庢惔?
        if settings.TUSHARE_ENABLED:
            # Tushare 閸氼垳鏁ら弮璁圭礉娴兼ê鍘涙担璺ㄦ暏 Tushare
            preferred_sources = ["tushare", "akshare", "baostock"]
            logger.info(f"棣冩惓 閼诧紕銈ㄩ崺铏诡攨娣団剝浼呴崥灞绢劄娴兼ê鍘涢弫鐗堝祦濠? Tushare > AKShare > BaoStock")
        else:
            # Tushare 缁備胶鏁ら弮璁圭礉娴ｈ法鏁?AKShare 閸?BaoStock
            preferred_sources = ["akshare", "baostock"]
            logger.info(f"棣冩惓 閼诧紕銈ㄩ崺铏诡攨娣団剝浼呴崥灞绢劄娴兼ê鍘涢弫鐗堝祦濠? AKShare > BaoStock (Tushare瀹歌尙顩﹂悽?")

        # 缁斿宓嗛崷銊ユ儙閸斻劌鎮楃亸婵婄槸娑撯偓濞嗏槄绱欐稉宥夋▎婵夌儑绱?        async def run_sync_with_sources():
            await multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources)

        asyncio.create_task(run_sync_with_sources())

        # 闁板秶鐤嗙拫鍐ㄥ閿涙矮绱崗鍫滃▏閻?CRON閿涘苯鍙惧▎鈥插▏閻?HH:MM
        if settings.SYNC_STOCK_BASICS_ENABLED:
            if settings.SYNC_STOCK_BASICS_CRON:
                # 婵″倹鐏夐幓鎰返娴滃摶ron鐞涖劏鎻?                scheduler.add_job(
                    lambda: multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources),
                    CronTrigger.from_crontab(settings.SYNC_STOCK_BASICS_CRON, timezone=settings.TIMEZONE),
                    id="basics_sync_service",
                    name="閼诧紕銈ㄩ崺铏诡攨娣団剝浼呴崥灞绢劄閿涘牆顦块弫鐗堝祦濠ф劧绱?
                )
                logger.info(f"棣冩惍 Stock basics sync scheduled by CRON: {settings.SYNC_STOCK_BASICS_CRON} ({settings.TIMEZONE})")
            else:
                hh, mm = (settings.SYNC_STOCK_BASICS_TIME or "06:30").split(":")
                scheduler.add_job(
                    lambda: multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources),
                    CronTrigger(hour=int(hh), minute=int(mm), timezone=settings.TIMEZONE),
                    id="basics_sync_service",
                    name="閼诧紕銈ㄩ崺铏诡攨娣団剝浼呴崥灞绢劄閿涘牆顦块弫鐗堝祦濠ф劧绱?
                )
                logger.info(f"棣冩惍 Stock basics sync scheduled daily at {settings.SYNC_STOCK_BASICS_TIME} ({settings.TIMEZONE})")

        # 鐎圭偞妞傜悰灞惧剰閸忋儱绨辨禒璇插閿涘牊鐦缁夋帪绱氶敍灞藉敶闁劏鍤滈崚銈勬唉閺勬挻妞傚▓?        if settings.QUOTES_INGEST_ENABLED:
            quotes_ingestion = QuotesIngestionService()
            await quotes_ingestion.ensure_indexes()
            scheduler.add_job(
                quotes_ingestion.run_once,  # coroutine function; AsyncIOScheduler will await it
                IntervalTrigger(seconds=settings.QUOTES_INGEST_INTERVAL_SECONDS, timezone=settings.TIMEZONE),
                id="quotes_ingestion_service",
                name="鐎圭偞妞傜悰灞惧剰閸忋儱绨遍張宥呭"
            )
            logger.info(f"閳?鐎圭偞妞傜悰灞惧剰閸忋儱绨辨禒璇插瀹告彃鎯庨崝? 濮?{settings.QUOTES_INGEST_INTERVAL_SECONDS}s")

        # Tushare缂佺喍绔撮弫鐗堝祦閸氬本顒炴禒璇插闁板秶鐤?        logger.info("棣冩敡 闁板秶鐤員ushare缂佺喍绔撮弫鐗堝祦閸氬本顒炴禒璇插...")

        # 閸╄櫣顢呮穱鈩冧紖閸氬本顒炴禒璇插
        scheduler.add_job(
            run_tushare_basic_info_sync,
            CronTrigger.from_crontab(settings.TUSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_basic_info_sync",
            name="閼诧紕銈ㄩ崺铏诡攨娣団剝浼呴崥灞绢劄閿涘湵ushare閿?,
            kwargs={"force_update": False}
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("tushare_basic_info_sync")
            logger.info(f"閳撮潻绗?Tushare閸╄櫣顢呮穱鈩冧紖閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.TUSHARE_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"棣冩惍 Tushare閸╄櫣顢呮穱鈩冧紖閸氬本顒炲鏌ュ帳缂? {settings.TUSHARE_BASIC_INFO_SYNC_CRON}")

        # 鐎圭偞妞傜悰灞惧剰閸氬本顒炴禒璇插
        scheduler.add_job(
            run_tushare_quotes_sync,
            CronTrigger.from_crontab(settings.TUSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_quotes_sync",
            name="鐎圭偞妞傜悰灞惧剰閸氬本顒為敍鍦眜share閿?
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("tushare_quotes_sync")
            logger.info(f"閳撮潻绗?Tushare鐞涘本鍎忛崥灞绢劄瀹稿弶鍧婇崝鐘辩稻閺嗗倸浠? {settings.TUSHARE_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"棣冩惐 Tushare鐞涘本鍎忛崥灞绢劄瀹告煡鍘ょ純? {settings.TUSHARE_QUOTES_SYNC_CRON}")

        # 閸樺棗褰堕弫鐗堝祦閸氬本顒炴禒璇插
        scheduler.add_job(
            run_tushare_historical_sync,
            CronTrigger.from_crontab(settings.TUSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_historical_sync",
            name="閸樺棗褰堕弫鐗堝祦閸氬本顒為敍鍦眜share閿?,
            kwargs={"incremental": True}
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("tushare_historical_sync")
            logger.info(f"閳撮潻绗?Tushare閸樺棗褰堕弫鐗堝祦閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.TUSHARE_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"棣冩惓 Tushare閸樺棗褰堕弫鐗堝祦閸氬本顒炲鏌ュ帳缂? {settings.TUSHARE_HISTORICAL_SYNC_CRON}")

        # 鐠愩垹濮熼弫鐗堝祦閸氬本顒炴禒璇插
        scheduler.add_job(
            run_tushare_financial_sync,
            CronTrigger.from_crontab(settings.TUSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_financial_sync",
            name="鐠愩垹濮熼弫鐗堝祦閸氬本顒為敍鍦眜share閿?
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_FINANCIAL_SYNC_ENABLED):
            scheduler.pause_job("tushare_financial_sync")
            logger.info(f"閳撮潻绗?Tushare鐠愩垹濮熼弫鐗堝祦閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.TUSHARE_FINANCIAL_SYNC_CRON}")
        else:
            logger.info(f"棣冩尩 Tushare鐠愩垹濮熼弫鐗堝祦閸氬本顒炲鏌ュ帳缂? {settings.TUSHARE_FINANCIAL_SYNC_CRON}")

        # 閻樿埖鈧焦顥呴弻銉ゆ崲閸?        scheduler.add_job(
            run_tushare_status_check,
            CronTrigger.from_crontab(settings.TUSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="tushare_status_check",
            name="閺佺増宓佸┃鎰Ц閹焦顥呴弻銉礄Tushare閿?
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_STATUS_CHECK_ENABLED):
            scheduler.pause_job("tushare_status_check")
            logger.info(f"閳撮潻绗?Tushare閻樿埖鈧焦顥呴弻銉ュ嚒濞ｈ濮炴担鍡樻畯閸? {settings.TUSHARE_STATUS_CHECK_CRON}")
        else:
            logger.info(f"棣冩敵 Tushare閻樿埖鈧焦顥呴弻銉ュ嚒闁板秶鐤? {settings.TUSHARE_STATUS_CHECK_CRON}")

        # AKShare缂佺喍绔撮弫鐗堝祦閸氬本顒炴禒璇插闁板秶鐤?        logger.info("棣冩敡 闁板秶鐤咥KShare缂佺喍绔撮弫鐗堝祦閸氬本顒炴禒璇插...")

        # 閸╄櫣顢呮穱鈩冧紖閸氬本顒炴禒璇插
        scheduler.add_job(
            run_akshare_basic_info_sync,
            CronTrigger.from_crontab(settings.AKSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_basic_info_sync",
            name="閼诧紕銈ㄩ崺铏诡攨娣団剝浼呴崥灞绢劄閿涘湏KShare閿?,
            kwargs={"force_update": False}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("akshare_basic_info_sync")
            logger.info(f"閳撮潻绗?AKShare閸╄櫣顢呮穱鈩冧紖閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"棣冩惍 AKShare閸╄櫣顢呮穱鈩冧紖閸氬本顒炲鏌ュ帳缂? {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")

        # 鐎圭偞妞傜悰灞惧剰閸氬本顒炴禒璇插
        scheduler.add_job(
            run_akshare_quotes_sync,
            CronTrigger.from_crontab(settings.AKSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_quotes_sync",
            name="鐎圭偞妞傜悰灞惧剰閸氬本顒為敍鍦揔Share閿?
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("akshare_quotes_sync")
            logger.info(f"閳撮潻绗?AKShare鐞涘本鍎忛崥灞绢劄瀹稿弶鍧婇崝鐘辩稻閺嗗倸浠? {settings.AKSHARE_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"棣冩惐 AKShare鐞涘本鍎忛崥灞绢劄瀹告煡鍘ょ純? {settings.AKSHARE_QUOTES_SYNC_CRON}")

        # 閸樺棗褰堕弫鐗堝祦閸氬本顒炴禒璇插
        scheduler.add_job(
            run_akshare_historical_sync,
            CronTrigger.from_crontab(settings.AKSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_historical_sync",
            name="閸樺棗褰堕弫鐗堝祦閸氬本顒為敍鍦揔Share閿?,
            kwargs={"incremental": True}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_historical_sync")
            logger.info(f"閳撮潻绗?AKShare閸樺棗褰堕弫鐗堝祦閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.AKSHARE_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"棣冩惓 AKShare閸樺棗褰堕弫鐗堝祦閸氬本顒炲鏌ュ帳缂? {settings.AKSHARE_HISTORICAL_SYNC_CRON}")

        # 鐠愩垹濮熼弫鐗堝祦閸氬本顒炴禒璇插
        scheduler.add_job(
            run_akshare_financial_sync,
            CronTrigger.from_crontab(settings.AKSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_financial_sync",
            name="鐠愩垹濮熼弫鐗堝祦閸氬本顒為敍鍦揔Share閿?
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_FINANCIAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_financial_sync")
            logger.info(f"閳撮潻绗?AKShare鐠愩垹濮熼弫鐗堝祦閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.AKSHARE_FINANCIAL_SYNC_CRON}")
        else:
            logger.info(f"棣冩尩 AKShare鐠愩垹濮熼弫鐗堝祦閸氬本顒炲鏌ュ帳缂? {settings.AKSHARE_FINANCIAL_SYNC_CRON}")

        # 閻樿埖鈧焦顥呴弻銉ゆ崲閸?        scheduler.add_job(
            run_akshare_status_check,
            CronTrigger.from_crontab(settings.AKSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="akshare_status_check",
            name="閺佺増宓佸┃鎰Ц閹焦顥呴弻銉礄AKShare閿?
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_STATUS_CHECK_ENABLED):
            scheduler.pause_job("akshare_status_check")
            logger.info(f"閳撮潻绗?AKShare閻樿埖鈧焦顥呴弻銉ュ嚒濞ｈ濮炴担鍡樻畯閸? {settings.AKSHARE_STATUS_CHECK_CRON}")
        else:
            logger.info(f"棣冩敵 AKShare閻樿埖鈧焦顥呴弻銉ュ嚒闁板秶鐤? {settings.AKSHARE_STATUS_CHECK_CRON}")

        # BaoStock缂佺喍绔撮弫鐗堝祦閸氬本顒炴禒璇插闁板秶鐤?        logger.info("棣冩敡 闁板秶鐤咮aoStock缂佺喍绔撮弫鐗堝祦閸氬本顒炴禒璇插...")

        # 閸╄櫣顢呮穱鈩冧紖閸氬本顒炴禒璇插
        scheduler.add_job(
            run_baostock_basic_info_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_basic_info_sync",
            name="閼诧紕銈ㄩ崺铏诡攨娣団剝浼呴崥灞绢劄閿涘湐aoStock閿?
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("baostock_basic_info_sync")
            logger.info(f"閳撮潻绗?BaoStock閸╄櫣顢呮穱鈩冧紖閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"棣冩惖 BaoStock閸╄櫣顢呮穱鈩冧紖閸氬本顒炲鏌ュ帳缂? {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")

        # 閺冾檻缁惧灝鎮撳銉ゆ崲閸斺槄绱欏▔銊﹀壈閿涙aoStock娑撳秵鏁幐浣哥杽閺冩儼顢戦幆鍜冪礆
        scheduler.add_job(
            run_baostock_daily_quotes_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_daily_quotes_sync",
            name="閺冾檻缁炬寧鏆熼幑顔兼倱濮濄儻绱橞aoStock閿?
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_DAILY_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("baostock_daily_quotes_sync")
            logger.info(f"閳撮潻绗?BaoStock閺冾檻缁惧灝鎮撳銉ュ嚒濞ｈ濮炴担鍡樻畯閸? {settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"棣冩惐 BaoStock閺冾檻缁惧灝鎮撳銉ュ嚒闁板秶鐤? {settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON} (濞夈劍鍓伴敍娆盿oStock娑撳秵鏁幐浣哥杽閺冩儼顢戦幆?")

        # 閸樺棗褰堕弫鐗堝祦閸氬本顒炴禒璇插
        scheduler.add_job(
            run_baostock_historical_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_historical_sync",
            name="閸樺棗褰堕弫鐗堝祦閸氬本顒為敍鍦攁oStock閿?
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("baostock_historical_sync")
            logger.info(f"閳撮潻绗?BaoStock閸樺棗褰堕弫鐗堝祦閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"棣冩惓 BaoStock閸樺棗褰堕弫鐗堝祦閸氬本顒炲鏌ュ帳缂? {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")

        # 閻樿埖鈧焦顥呴弻銉ゆ崲閸?        scheduler.add_job(
            run_baostock_status_check,
            CronTrigger.from_crontab(settings.BAOSTOCK_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="baostock_status_check",
            name="閺佺増宓佸┃鎰Ц閹焦顥呴弻銉礄BaoStock閿?
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_STATUS_CHECK_ENABLED):
            scheduler.pause_job("baostock_status_check")
            logger.info(f"閳撮潻绗?BaoStock閻樿埖鈧焦顥呴弻銉ュ嚒濞ｈ濮炴担鍡樻畯閸? {settings.BAOSTOCK_STATUS_CHECK_CRON}")
        else:
            logger.info(f"棣冩敵 BaoStock閻樿埖鈧焦顥呴弻銉ュ嚒闁板秶鐤? {settings.BAOSTOCK_STATUS_CHECK_CRON}")

        # 閺備即妞堥弫鐗堝祦閸氬本顒炴禒璇插闁板秶鐤嗛敍鍫滃▏閻⑺婯Share閸氬本顒為幍鈧張澶庡亗缁併劍鏌婇梻浼欑礆
        logger.info("棣冩敡 闁板秶鐤嗛弬浼存閺佺増宓侀崥灞绢劄娴犺濮?..")

        from app.worker.akshare_sync_service import get_akshare_sync_service

        async def run_news_sync():
            """鏉╂劘顢戦弬浼存閸氬本顒炴禒璇插 - 娴ｈ法鏁KShare閸氬本顒為懛顏堚偓澶庡亗閺備即妞?""
            try:
                logger.info("棣冩應 瀵偓婵鏌婇梻缁樻殶閹诡喖鎮撳銉礄AKShare - 娴犲懓鍤滈柅澶庡亗閿?..")
                service = await get_akshare_sync_service()
                result = await service.sync_news_data(
                    symbols=None,  # None + favorites_only=True 鐞涖劎銇氶崣顏勬倱濮濄儴鍤滈柅澶庡亗
                    max_news_per_stock=settings.NEWS_SYNC_MAX_PER_SOURCE,
                    favorites_only=True  # 閸欘亜鎮撳銉ㄥ殰闁鍋?                )
                logger.info(
                    f"閴?閺備即妞堥崥灞绢劄鐎瑰本鍨? "
                    f"婢跺嫮鎮妠result['total_processed']}閸欘亣鍤滈柅澶庡亗, "
                    f"閹存劕濮泏result['success_count']}閸? "
                    f"婢惰精瑙result['error_count']}閸? "
                    f"閺備即妞堥幀缁樻殶{result['news_count']}閺? "
                    f"閼版妞倇(datetime.utcnow() - result['start_time']).total_seconds():.2f}缁?
                )
            except Exception as e:
                logger.error(f"閴?閺備即妞堥崥灞绢劄婢惰精瑙? {e}", exc_info=True)

        # ==================== 濞擃垵鍋?缂囧氦鍋傞弫鐗堝祦闁板秶鐤?====================
        # 濞擃垵鍋傞崪宀€绶ㄩ懖锟犲櫚閻劍瀵滈棁鈧懢宄板絿+缂傛挸鐡ㄥΟ鈥崇础閿涘奔绗夐崘宥夊帳缂冾喖鐣鹃弮璺烘倱濮濄儰鎹㈤崝?        logger.info("棣冨殶棣冨殺 濞擃垵鍋傞弫鐗堝祦闁插洨鏁ら幐澶愭付閼惧嘲褰?缂傛挸鐡ㄥΟ鈥崇础")
        logger.info("棣冨毉棣冨毇 缂囧氦鍋傞弫鐗堝祦闁插洨鏁ら幐澶愭付閼惧嘲褰?缂傛挸鐡ㄥΟ鈥崇础")

        scheduler.add_job(
            run_news_sync,
            CronTrigger.from_crontab(settings.NEWS_SYNC_CRON, timezone=settings.TIMEZONE),
            id="news_sync",
            name="閺備即妞堥弫鐗堝祦閸氬本顒為敍鍦揔Share - 娴犲懓鍤滈柅澶庡亗閿?
        )
        if not settings.NEWS_SYNC_ENABLED:
            scheduler.pause_job("news_sync")
            logger.info(f"閳撮潻绗?閺備即妞堥弫鐗堝祦閸氬本顒炲鍙夊潑閸旂姳绲鹃弳鍌氫粻: {settings.NEWS_SYNC_CRON}")
        else:
            logger.info(f"棣冩應 閺備即妞堥弫鐗堝祦閸氬本顒炲鏌ュ帳缂冾噯绱欐禒鍛板殰闁鍋傞敍? {settings.NEWS_SYNC_CRON}")

        scheduler.start()

        # 鐠佸墽鐤嗙拫鍐ㄥ閸ｃ劌鐤勬笟瀣煂閺堝秴濮熸稉顓ㄧ礉娴犮儰绌禔PI閸欘垯浜掔粻锛勬倞娴犺濮?        set_scheduler_instance(scheduler)
        logger.info("閴?鐠嬪啫瀹抽崳銊︽箛閸斺€冲嚒閸掓繂顫愰崠?)
    except Exception as e:
        logger.error(f"閴?鐠嬪啫瀹抽崳銊ユ儙閸斻劌銇戠拹? {e}", exc_info=True)
        raise  # 閹舵稑鍤鍌氱埗閿涘矂妯嗗銏犵安閻劌鎯庨崝?
    try:
        yield
    finally:
        # 閸忔娊妫撮弮鑸电閻?        if scheduler:
            try:
                scheduler.shutdown(wait=False)
                logger.info("棣冩磧 Scheduler stopped")
            except Exception as e:
                logger.warning(f"Scheduler shutdown error: {e}")

        # 閸忔娊妫?UserService MongoDB 鏉╃偞甯?        try:
            from app.services.user_service import user_service
            user_service.close()
        except Exception as e:
            logger.warning(f"UserService cleanup error: {e}")

        await close_db()
        logger.info("TradingAgents FastAPI backend stopped")


# 閸掓稑缂揊astAPI鎼存梻鏁?app = FastAPI(
    title="TradingAgents-CN API",
    description="閼诧紕銈ㄩ崚鍡樼€芥稉搴㈠闁插繘妲﹂崚妤冮兇缂?API",
    version=get_version(),
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# 鐎瑰鍙忔稉顓㈡？娴?if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )

# CORS娑擃參妫挎禒?app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 閹垮秳缍旈弮銉ョ箶娑擃參妫挎禒?app.add_middleware(OperationLogMiddleware)


# 鐠囬攱鐪伴弮銉ョ箶娑擃參妫挎禒?@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # 鐠哄疇绻冮崑銉ユ倣濡偓閺屻儱鎷伴棃娆愨偓浣规瀮娴犳儼顕Ч鍌滄畱閺冦儱绻?    if request.url.path in ["/health", "/favicon.ico"] or request.url.path.startswith("/static"):
        response = await call_next(request)
        return response

    # 娴ｈ法鏁ebapi logger鐠佹澘缍嶇拠閿嬬湴
    logger = logging.getLogger("webapi")
    logger.info(f"棣冩敡 {request.method} {request.url.path} - 瀵偓婵顦╅悶?)

    response = await call_next(request)
    process_time = time.time() - start_time

    # 鐠佹澘缍嶇拠閿嬬湴鐎瑰本鍨?    status_emoji = "閴? if response.status_code < 400 else "閴?
    logger.info(f"{status_emoji} {request.method} {request.url.path} - 閻樿埖鈧? {response.status_code} - 閼版妞? {process_time:.3f}s")

    return response


# 閸忋劌鐪鍌氱埗婢跺嫮鎮?# 鐠囬攱鐪癐D/Trace-ID 娑擃參妫挎禒璁圭礄闂団偓娴ｆ粈璐熼張鈧径鏍х湴閿涘本鏂侀崷銊ュ毐閺佹澘绱℃稉顓㈡？娴犳湹绠ｉ崥搴礆
from app.middleware.request_id import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error occurred",
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )


# 濞村鐦粩顖滃仯 - 妤犲矁鐦夋稉顓㈡？娴犺埖妲搁崥锕€浼愭担?@app.get("/api/test-log")
async def test_log():
    """濞村鐦弮銉ョ箶娑擃參妫挎禒鑸垫Ц閸氾箑浼愭担?""
    print("棣冃?濞村鐦粩顖滃仯鐞氼偉鐨熼悽?- 鏉╂瑦娼☉鍫熶紖鎼存棁顕氶崙铏瑰箛閸︺劍甯堕崚璺哄酱")
    return {"message": "濞村鐦幋鎰", "timestamp": time.time()}

# 濞夈劌鍞界捄顖滄暠
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(screening.router, prefix="/api/screening", tags=["screening"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(favorites.router, prefix="/api", tags=["favorites"])
app.include_router(stocks_router.router, prefix="/api", tags=["stocks"])
app.include_router(multi_market_stocks_router.router, prefix="/api", tags=["multi-market"])
app.include_router(stock_data_router.router, prefix="/api/stock-data", tags=["stock-data"])
app.include_router(stock_sync_router.router, prefix="/api/stock-sync", tags=["stock-sync"])
app.include_router(tags.router, prefix="/api", tags=["tags"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(model_capabilities.router, prefix="/api/model-capabilities", tags=["model-capabilities"])
app.include_router(usage_statistics.router, prefix="/api/usage-statistics", tags=["usage-statistics"])
app.include_router(database.router, prefix="/api/system", tags=["database"])
app.include_router(cache.router, prefix="/api/cache", tags=["cache"])
app.include_router(operation_logs.router, prefix="/api/system", tags=["operation_logs"])
app.include_router(logs.router, prefix="/api/system", tags=["logs"])
# 閺傛澘顤冮敍姘遍兇缂佺喖鍘ょ純顔煎涧鐠囩粯鎲崇憰?from app.routers import system_config as system_config_router
app.include_router(system_config_router.router, prefix="/api/system", tags=["system"])

# 闁氨鐓″Ο鈥虫健閿涘湩EST + SSE閿?app.include_router(notifications_router.router, prefix="/api", tags=["notifications"])

# 棣冩暉 WebSocket 闁氨鐓″Ο鈥虫健閿涘牊娴涙禒?SSE + Redis PubSub閿?app.include_router(websocket_notifications_router.router, prefix="/api", tags=["websocket"])

# 鐎规碍妞傛禒璇插缁狅紕鎮?app.include_router(scheduler_router.router, prefix="/api/scheduler", tags=["scheduler"])

app.include_router(sse.router, prefix="/api/stream", tags=["streaming"])
app.include_router(sync_router.router, prefix="/api/sync")
app.include_router(multi_source_sync.router, prefix="/api/multi-source-sync")
app.include_router(paper_router.router, prefix="/api", tags=["paper"])
app.include_router(tushare_init.router, prefix="/api", tags=["tushare-init"])
app.include_router(akshare_init.router, prefix="/api", tags=["akshare-init"])
app.include_router(baostock_init.router, prefix="/api", tags=["baostock-init"])
app.include_router(historical_data.router, prefix="/api/historical-data", tags=["historical-data"])
app.include_router(multi_period_sync.router, prefix="/api/multi-period-sync", tags=["multi-period-sync"])
app.include_router(financial_data.router, prefix="/api/financial-data", tags=["financial-data"])
app.include_router(news_data.router, prefix="/api/news-data", tags=["news-data"])
app.include_router(social_media.router, prefix="/api/social-media", tags=["social-media"])
app.include_router(internal_messages.router, prefix="/api/internal-messages", tags=["internal-messages"])


@app.get("/")
async def root():
    """閺嶇鐭惧鍕剁礉鏉╂柨娲朅PI娣団剝浼?""
    print("棣冨綌 閺嶇鐭惧鍕潶鐠佸潡妫?)
    return {
        "name": "TradingAgents-CN API",
        "version": get_version(),
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
        reload_dirs=["app"] if settings.DEBUG else None,
        reload_excludes=[
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".git",
            ".pytest_cache",
            "*.log",
            "*.tmp"
        ] if settings.DEBUG else None,
        reload_includes=["*.py"] if settings.DEBUG else None
    )