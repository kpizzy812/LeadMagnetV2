# personas/persona_factory.py

from typing import Dict, Optional
from .base.base_persona import BasePersona, PersonaRole, ProjectKnowledge
from .base.basic_man import BasicManPersona
from .base.basic_woman import BasicWomanPersona
from .base.hyip_man import HyipManPersona
from loguru import logger


class PersonaFactory:
    """Фабрика для создания персон"""

    _persona_classes = {
        PersonaRole.BASIC_MAN: BasicManPersona,
        PersonaRole.BASIC_WOMAN: BasicWomanPersona,
        PersonaRole.HYIP_MAN: HyipManPersona,
        # PersonaRole.HYIP_WOMAN: HyipWomanPersona,  # Добавим позже
        # PersonaRole.INVESTOR_MAN: InvestorManPersona,  # Добавим позже
    }

    @classmethod
    def create_persona(
            cls,
            persona_type: PersonaRole,
            ref_link: str,
            project_knowledge: ProjectKnowledge
    ) -> BasePersona:
        """Создание персоны по типу"""

        if persona_type not in cls._persona_classes:
            logger.error(f"❌ Неизвестный тип персоны: {persona_type}")
            raise ValueError(f"Unsupported persona type: {persona_type}")

        persona_class = cls._persona_classes[persona_type]

        try:
            persona = persona_class(ref_link=ref_link, project_knowledge=project_knowledge)
            logger.info(f"✅ Создана персона: {persona_type} ({persona.traits.name})")
            return persona

        except Exception as e:
            logger.error(f"❌ Ошибка создания персоны {persona_type}: {e}")
            raise

    @classmethod
    def get_available_personas(cls) -> Dict[PersonaRole, str]:
        """Получение списка доступных персон"""
        result = {}
        for persona_type, persona_class in cls._persona_classes.items():
            # Создаем временную персону для получения имени
            temp_knowledge = ProjectKnowledge(
                project_name="Test",
                description="Test",
                advantages=[],
                risks=[],
                target_audience="Test",
                support_contact="Test",
                chat_link=None,
                typical_returns="Test",
                minimum_investment="Test"
            )
            temp_persona = persona_class("test_link", temp_knowledge)
            result[persona_type] = temp_persona.traits.name

        return result

    @classmethod
    def register_persona_class(cls, persona_type: PersonaRole, persona_class: type):
        """Регистрация нового класса персоны (для расширений)"""
        if not issubclass(persona_class, BasePersona):
            raise ValueError("Persona class must inherit from BasePersona")

        cls._persona_classes[persona_type] = persona_class
        logger.info(f"✅ Зарегистрирована новая персона: {persona_type}")


class ProjectKnowledgeManager:
    """Менеджер знаний о проектах"""

    def __init__(self):
        self._projects: Dict[str, ProjectKnowledge] = {}

    def add_project(self, project_id: str, knowledge: ProjectKnowledge):
        """Добавление проекта"""
        self._projects[project_id] = knowledge
        logger.info(f"✅ Добавлен проект: {project_id} ({knowledge.project_name})")

    def get_project(self, project_id: str) -> Optional[ProjectKnowledge]:
        """Получение проекта"""
        return self._projects.get(project_id)

    def get_all_projects(self) -> Dict[str, ProjectKnowledge]:
        """Получение всех проектов"""
        return self._projects.copy()

    def remove_project(self, project_id: str):
        """Удаление проекта"""
        if project_id in self._projects:
            del self._projects[project_id]
            logger.info(f"🗑️ Удален проект: {project_id}")


# Глобальные экземпляры
persona_factory = PersonaFactory()
project_knowledge_manager = ProjectKnowledgeManager()


# Функции-помощники для упрощения использования
def create_persona_for_session(
        session_name: str,
        persona_type: PersonaRole,
        ref_link: str,
        project_id: str
) -> BasePersona:
    """Создание персоны для сессии"""

    project_knowledge = project_knowledge_manager.get_project(project_id)
    if not project_knowledge:
        raise ValueError(f"Project {project_id} not found")

    persona = persona_factory.create_persona(persona_type, ref_link, project_knowledge)

    logger.info(f"🎭 Персона {persona.traits.name} ({persona_type}) создана для сессии {session_name}")

    return persona


def setup_default_project():
    """Настройка проекта по умолчанию (для разработки)"""
    default_project = ProjectKnowledge(
        project_name="CryptoBot",
        description="Автоматизированная торговля криптовалютами с использованием ИИ",
        advantages=[
            "Пассивный доход 24/7",
            "Минимальные риски благодаря ИИ",
            "Простота использования",
            "Быстрые выводы средств",
            "Прозрачная статистика"
        ],
        risks=[
            "Волатильность криптовалют",
            "Технические сбои платформы",
            "Изменения в регулировании"
        ],
        target_audience="Люди заинтересованные в пассивном доходе",
        support_contact="@cryptobot_support",
        chat_link="https://t.me/cryptobot_chat",
        typical_returns="5-15% в месяц",
        minimum_investment="от $10"
    )

    project_knowledge_manager.add_project("default", default_project)
    logger.info("🚀 Настроен проект по умолчанию")