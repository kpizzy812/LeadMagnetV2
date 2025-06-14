# core/handlers/message_handler.py - НОВАЯ УПРОЩЕННАЯ ВЕРСИЯ

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import select, update, and_

from config.settings.base import settings
from storage.database import get_db
from storage.models.base import Session, SessionStatus, Conversation, ConversationStatus, MessageApproval, \
    ApprovalStatus
from core.scanning.retrospective_scanner import retrospective_scanner
from core.engine.conversation_manager import conversation_manager
from loguru import logger


class MessageHandler:
    """
    Упрощенный обработчик сообщений для ретроспективной системы.
    Больше НЕ обрабатывает события в реальном времени.
    Только управляет ретроспективным сканированием и одобрениями.
    """

    def __init__(self):
        self.is_running = False
        self.session_stats: Dict[str, Dict] = {}

    async def initialize(self):
        """Инициализация упрощенного обработчика"""
        try:
            logger.info("🔄 Инициализация упрощенного MessageHandler...")

            # Запускаем ретроспективный сканер
            await retrospective_scanner.start_scanning()

            # Запускаем воркер обработки одобрений
            asyncio.create_task(self._approval_worker())

            # Запускаем обновление статистики
            asyncio.create_task(self._stats_update_loop())

            self.is_running = True
            logger.success("✅ Упрощенный MessageHandler инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации MessageHandler: {e}")
            raise

    async def shutdown(self):
        """Завершение работы"""
        logger.info("🛑 Завершение работы MessageHandler...")

        self.is_running = False

        # Останавливаем ретроспективный сканер
        await retrospective_scanner.stop_scanning()

        logger.info("✅ MessageHandler завершен")

    async def approve_conversation(self, conversation_id: int, admin_id: int, comment: Optional[str] = None) -> bool:
        """Одобрение диалога админом"""
        try:
            async with get_db() as db:
                # Обновляем статус диалога
                await db.execute(
                    update(Conversation).where(
                        Conversation.id == conversation_id
                    ).values(
                        admin_approved=True,
                        status=ConversationStatus.APPROVED,
                        requires_approval=False,
                        updated_at=datetime.utcnow()
                    )
                )

                # Записываем одобрение
                approval = MessageApproval(
                    conversation_id=conversation_id,
                    status=ApprovalStatus.APPROVED,
                    approved_by_admin_id=admin_id,
                    approved_at=datetime.utcnow(),
                    admin_comment=comment
                )
                db.add(approval)

                await db.commit()

                logger.info(f"✅ Диалог {conversation_id} одобрен админом {admin_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка одобрения диалога {conversation_id}: {e}")
            return False

    async def reject_conversation(self, conversation_id: int, admin_id: int, comment: Optional[str] = None) -> bool:
        """Отклонение диалога админом"""
        try:
            async with get_db() as db:
                # Обновляем статус диалога
                await db.execute(
                    update(Conversation).where(
                        Conversation.id == conversation_id
                    ).values(
                        status=ConversationStatus.BLOCKED,
                        requires_approval=False,
                        updated_at=datetime.utcnow()
                    )
                )

                # Записываем отклонение
                approval = MessageApproval(
                    conversation_id=conversation_id,
                    status=ApprovalStatus.REJECTED,
                    approved_by_admin_id=admin_id,
                    approved_at=datetime.utcnow(),
                    admin_comment=comment
                )
                db.add(approval)

                await db.commit()

                logger.info(f"🚫 Диалог {conversation_id} отклонен админом {admin_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка отклонения диалога {conversation_id}: {e}")
            return False

    async def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Получение диалогов ожидающих одобрения"""
        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Conversation).where(
                        and_(
                            Conversation.requires_approval == True,
                            Conversation.admin_approved == False,
                            Conversation.status == ConversationStatus.PENDING_APPROVAL
                        )
                    ).order_by(Conversation.created_at.desc())
                )

                conversations = result.scalars().all()

                pending_list = []
                for conv in conversations:
                    # Получаем последнее сообщение от лида
                    last_msg_result = await db.execute(
                        select(Message).where(
                            and_(
                                Message.conversation_id == conv.id,
                                Message.is_from_lead == True
                            )
                        ).order_by(Message.timestamp.desc()).limit(1)
                    )

                    last_message = last_msg_result.scalar_one_or_none()

                    pending_list.append({
                        "conversation_id": conv.id,
                        "lead_username": conv.lead_username,
                        "session_name": conv.session_name,
                        "created_at": conv.created_at,
                        "last_message": last_message.content if last_message else None,
                        "last_message_time": last_message.timestamp if last_message else None,
                        "total_messages": conv.total_messages_received
                    })

                return pending_list

        except Exception as e:
            logger.error(f"❌ Ошибка получения ожидающих одобрения: {e}")
            return []

    async def force_scan_now(self) -> Dict[str, Any]:
        """Принудительное сканирование (для админов)"""
        try:
            return await retrospective_scanner.force_scan_now()
        except Exception as e:
            logger.error(f"❌ Ошибка принудительного сканирования: {e}")
            return {"error": str(e)}

    async def pause_session_scanning(self, session_name: str) -> bool:
        """Приостановка сканирования конкретной сессии"""
        try:
            async with get_db() as db:
                await db.execute(
                    update(Session).where(
                        Session.session_name == session_name
                    ).values(
                        ai_enabled=False,
                        updated_at=datetime.utcnow()
                    )
                )
                await db.commit()

                logger.info(f"⏸️ Сканирование сессии {session_name} приостановлено")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка приостановки сканирования {session_name}: {e}")
            return False

    async def resume_session_scanning(self, session_name: str) -> bool:
        """Возобновление сканирования сессии"""
        try:
            async with get_db() as db:
                await db.execute(
                    update(Session).where(
                        Session.session_name == session_name
                    ).values(
                        ai_enabled=True,
                        updated_at=datetime.utcnow()
                    )
                )
                await db.commit()

                logger.info(f"▶️ Сканирование сессии {session_name} возобновлено")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка возобновления сканирования {session_name}: {e}")
            return False

    async def get_session_status(self, session_name: str) -> Dict[str, Any]:
        """Получение статуса сессии"""
        try:
            async with get_db() as db:
                # Основная информация о сессии
                session_result = await db.execute(
                    select(Session).where(Session.session_name == session_name)
                )
                session = session_result.scalar_one_or_none()

                if not session:
                    return {"error": "Session not found"}

                # Статистика диалогов
                dialogs_result = await db.execute(
                    select(Conversation).where(Conversation.session_name == session_name)
                )
                dialogs = dialogs_result.scalars().all()

                # Группируем по статусам
                status_counts = {}
                for dialog in dialogs:
                    status = dialog.status.value
                    status_counts[status] = status_counts.get(status, 0) + 1

                # Ожидающие одобрения
                pending_count = len([d for d in dialogs if d.requires_approval and not d.admin_approved])

                return {
                    "session_name": session_name,
                    "status": session.status.value,
                    "ai_enabled": session.ai_enabled,
                    "total_conversations": len(dialogs),
                    "pending_approvals": pending_count,
                    "status_breakdown": status_counts,
                    "last_activity": session.last_activity.isoformat() if session.last_activity else None,
                    "created_at": session.created_at.isoformat(),
                    "scanning_enabled": session.ai_enabled and session.status == SessionStatus.ACTIVE
                }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса сессии {session_name}: {e}")
            return {"error": str(e)}

    async def get_realtime_stats(self) -> Dict[str, Any]:
        """Получение статистики в реальном времени"""
        try:
            # Базовая статистика
            async with get_db() as db:
                # Активные сессии
                active_sessions_result = await db.execute(
                    select(Session).where(
                        and_(
                            Session.status == SessionStatus.ACTIVE,
                            Session.ai_enabled == True
                        )
                    )
                )
                active_sessions = active_sessions_result.scalars().all()

                # Диалоги ожидающие одобрения
                pending_result = await db.execute(
                    select(Conversation).where(
                        and_(
                            Conversation.requires_approval == True,
                            Conversation.admin_approved == False
                        )
                    )
                )
                pending_conversations = len(pending_result.scalars().all())

            # Статистика сканера
            scanner_stats = retrospective_scanner.get_stats()

            return {
                "system_type": "retrospective_scanning",
                "active_sessions": len(active_sessions),
                "pending_approvals": pending_conversations,
                "scanner_running": retrospective_scanner.is_running,
                "scanner_stats": scanner_stats,
                "last_updated": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {"error": str(e)}

    async def _approval_worker(self):
        """Воркер для обработки одобрений и таймаутов"""
        while self.is_running:
            try:
                await self._process_approval_timeouts()
                await asyncio.sleep(60)  # Проверяем каждую минуту
            except Exception as e:
                logger.error(f"❌ Ошибка в воркере одобрений: {e}")
                await asyncio.sleep(60)

    async def _process_approval_timeouts(self):
        """Обработка таймаутов одобрений"""
        try:
            # Автоматически отклоняем диалоги, которые ждут одобрения более 24 часов
            timeout_threshold = datetime.utcnow() - timedelta(hours=24)

            async with get_db() as db:
                timeout_conversations = await db.execute(
                    select(Conversation).where(
                        and_(
                            Conversation.requires_approval == True,
                            Conversation.admin_approved == False,
                            Conversation.created_at < timeout_threshold
                        )
                    )
                )

                conversations = timeout_conversations.scalars().all()

                for conv in conversations:
                    # Отмечаем как отклоненные по таймауту
                    await db.execute(
                        update(Conversation).where(
                            Conversation.id == conv.id
                        ).values(
                            status=ConversationStatus.BLOCKED,
                            requires_approval=False,
                            updated_at=datetime.utcnow()
                        )
                    )

                    # Записываем отклонение по таймауту
                    approval = MessageApproval(
                        conversation_id=conv.id,
                        status=ApprovalStatus.TIMEOUT,
                        approved_at=datetime.utcnow(),
                        admin_comment="Автоматическое отклонение по таймауту (24 часа)"
                    )
                    db.add(approval)

                if conversations:
                    await db.commit()
                    logger.info(f"⏰ Автоматически отклонено {len(conversations)} диалогов по таймауту")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки таймаутов одобрений: {e}")

    async def _stats_update_loop(self):
        """Цикл обновления статистики"""
        while self.is_running:
            try:
                await self._update_session_stats()
                await asyncio.sleep(300)  # Обновляем каждые 5 минут
            except Exception as e:
                logger.error(f"❌ Ошибка обновления статистики: {e}")
                await asyncio.sleep(300)

    async def _update_session_stats(self):
        """Обновление статистики сессий"""
        try:
            async with get_db() as db:
                sessions_result = await db.execute(
                    select(Session).where(Session.status == SessionStatus.ACTIVE)
                )
                sessions = sessions_result.scalars().all()

                for session in sessions:
                    session_name = session.session_name

                    # Считаем диалоги
                    dialogs_result = await db.execute(
                        select(Conversation).where(Conversation.session_name == session_name)
                    )
                    dialogs = dialogs_result.scalars().all()

                    # Статистика
                    total_conversations = len(dialogs)
                    active_conversations = len([d for d in dialogs if d.status == ConversationStatus.ACTIVE])
                    pending_approvals = len([d for d in dialogs if d.requires_approval and not d.admin_approved])

                    self.session_stats[session_name] = {
                        "total_conversations": total_conversations,
                        "active_conversations": active_conversations,
                        "pending_approvals": pending_approvals,
                        "ai_enabled": session.ai_enabled,
                        "last_updated": datetime.utcnow().isoformat()
                    }

        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики сессий: {e}")

    # Методы для совместимости со старым кодом (заглушки):

    async def handle_incoming_message(self, session_name: str, event):
        """Заглушка для совместимости - теперь обработка через ретроспективное сканирование"""
        logger.debug(f"📨 handle_incoming_message вызван для {session_name} (игнорируется в ретроспективной системе)")

    async def add_session(self, session: Session):
        """Заглушка для совместимости"""
        logger.debug(f"📝 add_session вызван для {session.session_name} (не требуется в ретроспективной системе)")

    async def remove_session(self, session_name: str):
        """Заглушка для совместимости"""
        logger.debug(f"📝 remove_session вызван для {session_name} (не требуется в ретроспективной системе)")

    async def cleanup_inactive_sessions(self):
        """Заглушка для совместимости"""
        logger.debug("🧹 cleanup_inactive_sessions вызван (не требуется в ретроспективной системе)")
        return 0

    async def get_active_sessions(self) -> List[str]:
        """Получение списка активных сессий для совместимости"""
        try:
            async with get_db() as db:
                result = await db.execute(
                    select(Session.session_name).where(
                        and_(
                            Session.status == SessionStatus.ACTIVE,
                            Session.ai_enabled == True
                        )
                    )
                )
                return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"❌ Ошибка получения активных сессий: {e}")
            return []

    async def emergency_disconnect_all(self):
        """Заглушка для совместимости"""
        logger.info("🚨 emergency_disconnect_all вызван (не требуется в ретроспективной системе)")

    async def force_reconnect_all(self):
        """Заглушка для совместимости"""
        logger.info("🔄 force_reconnect_all вызван (не требуется в ретроспективной системе)")

    async def get_recovery_stats(self) -> Dict[str, Any]:
        """Заглушка для совместимости"""
        return {
            "system_type": "retrospective_scanning",
            "message": "Recovery stats не применимы для ретроспективной системы"
        }


# Глобальный экземпляр обработчика
message_handler = MessageHandler()