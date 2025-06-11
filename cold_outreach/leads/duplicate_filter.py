# cold_outreach/leads/duplicate_filter.py

from typing import Set, Dict, Optional
from sqlalchemy import select, func
from storage.database import get_db
from storage.models.cold_outreach import OutreachLead
from loguru import logger


class DuplicateFilter:
    """Фильтр дубликатов лидов"""

    def __init__(self):
        # Кэш username'ов по спискам для быстрой проверки
        self.username_cache: Dict[int, Set[str]] = {}
        # Глобальный кэш всех username'ов
        self.global_username_cache: Set[str] = set()

    async def initialize(self):
        """Инициализация фильтра дубликатов"""
        try:
            await self._build_cache()
            logger.info("✅ DuplicateFilter инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации DuplicateFilter: {e}")
            raise

    async def _build_cache(self):
        """Построение кэша существующих username'ов"""

        try:
            async with get_db() as db:
                # Загружаем все существующие username'ы
                result = await db.execute(
                    select(OutreachLead.username, OutreachLead.lead_list_id)
                )

                usernames_data = result.fetchall()

                for username, list_id in usernames_data:
                    # Добавляем в кэш списка
                    if list_id not in self.username_cache:
                        self.username_cache[list_id] = set()

                    normalized_username = self._normalize_username(username)
                    self.username_cache[list_id].add(normalized_username)

                    # Добавляем в глобальный кэш
                    self.global_username_cache.add(normalized_username)

                total_usernames = len(self.global_username_cache)
                total_lists = len(self.username_cache)

                logger.info(f"📊 Загружено {total_usernames} username'ов из {total_lists} списков")

        except Exception as e:
            logger.error(f"❌ Ошибка построения кэша дубликатов: {e}")

    def _normalize_username(self, username: str) -> str:
        """Нормализация username для сравнения"""
        try:
            return str(username).strip().lower().lstrip("@")
        except Exception:
            return username

    async def is_duplicate(self, username: str, list_id: int) -> bool:
        """Проверка является ли username дубликатом в конкретном списке"""

        try:
            normalized_username = self._normalize_username(username)

            # Проверяем кэш списка
            if list_id in self.username_cache:
                return normalized_username in self.username_cache[list_id]

            # Если кэш пуст для списка, проверяем БД напрямую
            return await self._check_duplicate_in_db(normalized_username, list_id)

        except Exception as e:
            logger.error(f"❌ Ошибка проверки дубликата {username}: {e}")
            return False

    async def is_global_duplicate(self, username: str) -> bool:
        """Проверка является ли username дубликатом во всей системе"""

        try:
            normalized_username = self._normalize_username(username)

            # Проверяем глобальный кэш
            if normalized_username in self.global_username_cache:
                return True

            # Если нет в кэше, проверяем БД
            async with get_db() as db:
                result = await db.execute(
                    select(func.count(OutreachLead.id))
                    .where(OutreachLead.username == normalized_username)
                )
                count = result.scalar() or 0
                return count > 0

        except Exception as e:
            logger.error(f"❌ Ошибка проверки глобального дубликата {username}: {e}")
            return False

    async def _check_duplicate_in_db(self, username: str, list_id: int) -> bool:
        """Проверка дубликата в БД для конкретного списка"""

        try:
            async with get_db() as db:
                result = await db.execute(
                    select(func.count(OutreachLead.id))
                    .where(
                        OutreachLead.username == username,
                        OutreachLead.lead_list_id == list_id
                    )
                )
                count = result.scalar() or 0
                return count > 0

        except Exception as e:
            logger.error(f"❌ Ошибка проверки дубликата в БД: {e}")
            return False

    async def add_username(self, username: str, list_id: int):
        """Добавление username в кэш"""

        try:
            normalized_username = self._normalize_username(username)

            # Добавляем в кэш списка
            if list_id not in self.username_cache:
                self.username_cache[list_id] = set()

            self.username_cache[list_id].add(normalized_username)

            # Добавляем в глобальный кэш
            self.global_username_cache.add(normalized_username)

        except Exception as e:
            logger.error(f"❌ Ошибка добавления username {username} в кэш: {e}")

    async def remove_username(self, username: str, list_id: int):
        """Удаление username из кэша"""

        try:
            normalized_username = self._normalize_username(username)

            # Удаляем из кэша списка
            if list_id in self.username_cache:
                self.username_cache[list_id].discard(normalized_username)

            # Проверяем нужно ли удалять из глобального кэша
            # (если username больше нет ни в одном списке)
            should_remove_global = True
            for cache_set in self.username_cache.values():
                if normalized_username in cache_set:
                    should_remove_global = False
                    break

            if should_remove_global:
                self.global_username_cache.discard(normalized_username)

        except Exception as e:
            logger.error(f"❌ Ошибка удаления username {username} из кэша: {e}")

    async def find_duplicates_in_list(self, list_id: int) -> Dict[str, list]:
        """Поиск всех дубликатов внутри списка"""

        try:
            async with get_db() as db:
                # Получаем все username'ы из списка с группировкой
                result = await db.execute(
                    select(
                        OutreachLead.username,
                        func.count(OutreachLead.id).label('count'),
                        func.array_agg(OutreachLead.id).label('lead_ids')
                    )
                    .where(OutreachLead.lead_list_id == list_id)
                    .group_by(OutreachLead.username)
                    .having(func.count(OutreachLead.id) > 1)
                )

                duplicates = {}
                for row in result.fetchall():
                    username, count, lead_ids = row
                    duplicates[username] = {
                        'count': count,
                        'lead_ids': lead_ids
                    }

                return duplicates

        except Exception as e:
            logger.error(f"❌ Ошибка поиска дубликатов в списке {list_id}: {e}")
            return {}

    async def find_cross_list_duplicates(self) -> Dict[str, list]:
        """Поиск дубликатов между разными списками"""

        try:
            async with get_db() as db:
                # Находим username'ы которые есть в нескольких списках
                result = await db.execute(
                    select(
                        OutreachLead.username,
                        func.count(func.distinct(OutreachLead.lead_list_id)).label('lists_count'),
                        func.array_agg(func.distinct(OutreachLead.lead_list_id)).label('list_ids')
                    )
                    .group_by(OutreachLead.username)
                    .having(func.count(func.distinct(OutreachLead.lead_list_id)) > 1)
                )

                cross_duplicates = {}
                for row in result.fetchall():
                    username, lists_count, list_ids = row
                    cross_duplicates[username] = {
                        'lists_count': lists_count,
                        'list_ids': list_ids
                    }

                return cross_duplicates

        except Exception as e:
            logger.error(f"❌ Ошибка поиска межсписочных дубликатов: {e}")
            return {}

    async def remove_duplicates_from_list(self, list_id: int, keep_first: bool = True) -> int:
        """Удаление дубликатов из списка"""

        try:
            duplicates = await self.find_duplicates_in_list(list_id)
            removed_count = 0

            async with get_db() as db:
                for username, duplicate_info in duplicates.items():
                    lead_ids = duplicate_info['lead_ids']

                    if keep_first:
                        # Оставляем первый (самый старый), удаляем остальные
                        ids_to_remove = lead_ids[1:]
                    else:
                        # Оставляем последний (самый новый), удаляем остальные
                        ids_to_remove = lead_ids[:-1]

                    # Помечаем как заблокированные вместо удаления
                    from sqlalchemy import update
                    await db.execute(
                        update(OutreachLead)
                        .where(OutreachLead.id.in_(ids_to_remove))
                        .values(
                            is_blocked=True,
                            block_reason="duplicate_removed"
                        )
                    )

                    removed_count += len(ids_to_remove)

                    # Обновляем кэш
                    if keep_first:
                        # Убираем дубликаты из кэша, оставляем один
                        pass  # Один экземпляр остается

                await db.commit()

            logger.info(f"🧹 Удалено {removed_count} дубликатов из списка {list_id}")

            # Обновляем кэш
            await self._rebuild_list_cache(list_id)

            return removed_count

        except Exception as e:
            logger.error(f"❌ Ошибка удаления дубликатов из списка {list_id}: {e}")
            return 0

    async def _rebuild_list_cache(self, list_id: int):
        """Перестроение кэша для конкретного списка"""

        try:
            async with get_db() as db:
                # Очищаем старый кэш списка
                if list_id in self.username_cache:
                    del self.username_cache[list_id]

                # Загружаем актуальные данные
                result = await db.execute(
                    select(OutreachLead.username)
                    .where(
                        OutreachLead.lead_list_id == list_id,
                        OutreachLead.is_blocked == False
                    )
                )

                usernames = result.scalars().all()

                # Создаем новый кэш
                self.username_cache[list_id] = {
                    self._normalize_username(username) for username in usernames
                }

        except Exception as e:
            logger.error(f"❌ Ошибка перестроения кэша списка {list_id}: {e}")

    async def get_duplicate_stats(self) -> Dict[str, any]:
        """Получение статистики дубликатов"""

        try:
            stats = {
                "total_usernames_in_cache": len(self.global_username_cache),
                "lists_in_cache": len(self.username_cache),
                "duplicates_within_lists": {},
                "cross_list_duplicates_count": 0
            }

            # Статистика по спискам
            for list_id, usernames in self.username_cache.items():
                stats["duplicates_within_lists"][list_id] = len(usernames)

            # Межсписочные дубликаты
            cross_duplicates = await self.find_cross_list_duplicates()
            stats["cross_list_duplicates_count"] = len(cross_duplicates)

            return stats

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики дубликатов: {e}")
            return {
                "total_usernames_in_cache": 0,
                "lists_in_cache": 0,
                "duplicates_within_lists": {},
                "cross_list_duplicates_count": 0
            }

    async def refresh_cache(self):
        """Полное обновление кэша"""

        try:
            # Очищаем все кэши
            self.username_cache.clear()
            self.global_username_cache.clear()

            # Перестраиваем кэш
            await self._build_cache()

            logger.info("🔄 Кэш дубликатов полностью обновлен")

        except Exception as e:
            logger.error(f"❌ Ошибка обновления кэша дубликатов: {e}")

    def get_cache_size(self) -> Dict[str, int]:
        """Получение размера кэша"""

        try:
            return {
                "global_cache_size": len(self.global_username_cache),
                "list_caches_count": len(self.username_cache),
                "total_list_usernames": sum(len(usernames) for usernames in self.username_cache.values())
            }

        except Exception as e:
            logger.error(f"❌ Ошибка получения размера кэша: {e}")
            return {"global_cache_size": 0, "list_caches_count": 0, "total_list_usernames": 0}

# Глобальный экземпляр фильтра дубликатов
duplicate_filter = DuplicateFilter()