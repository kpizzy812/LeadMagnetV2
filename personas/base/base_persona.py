# personas/base/base_persona.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class CommunicationStyle(str, Enum):
    """Стили общения"""
    CASUAL = "casual"
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    ENTHUSIASTIC = "enthusiastic"
    CAUTIOUS = "cautious"


class PersonaRole(str, Enum):
    """Роли персон"""
    BASIC_MAN = "basic_man"
    BASIC_WOMAN = "basic_woman"
    HYIP_MAN = "hyip_man"
    HYIP_WOMAN = "hyip_woman"
    INVESTOR_MAN = "investor_man"


@dataclass
class PersonaTraits:
    """Черты персоны"""
    name: str
    age_range: str
    occupation: str
    experience_level: str
    risk_tolerance: str
    communication_style: CommunicationStyle
    typical_phrases: List[str]
    emoji_usage: str  # low, medium, high
    grammar_style: str  # perfect, casual, mistakes
    response_patterns: Dict[str, List[str]]


@dataclass
class ProjectKnowledge:
    """Знания о проекте"""
    project_name: str
    description: str
    advantages: List[str]
    risks: List[str]
    target_audience: str
    support_contact: str
    chat_link: Optional[str]
    typical_returns: str
    minimum_investment: str


class BasePersona(ABC):
    """Базовый класс для всех персон"""

    def __init__(self, ref_link: str, project_knowledge: ProjectKnowledge):
        self.ref_link = ref_link
        self.project_knowledge = project_knowledge
        self.traits = self._define_traits()

    @property
    @abstractmethod
    def persona_type(self) -> PersonaRole:
        """Тип персоны"""
        pass

    @abstractmethod
    def _define_traits(self) -> PersonaTraits:
        """Определение черт персоны"""
        pass

    @abstractmethod
    def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Получение системного промпта"""
        pass

    def get_funnel_stage_instruction(self, stage: str, context: Dict[str, Any]) -> str:
        """Получение инструкции для конкретного этапа воронки"""
        instructions = {
            "initial_contact": self._get_initial_contact_instruction(context),
            "trust_building": self._get_trust_building_instruction(context),
            "project_inquiry": self._get_project_inquiry_instruction(context),
            "interest_qualification": self._get_interest_qualification_instruction(context),
            "presentation": self._get_presentation_instruction(context),
            "objection_handling": self._get_objection_handling_instruction(context),
            "conversion": self._get_conversion_instruction(context),
            "post_conversion": self._get_post_conversion_instruction(context),
        }
        return instructions.get(stage, "Продолжай естественное общение.")

    @abstractmethod
    def _get_initial_contact_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция для начального контакта"""
        pass

    @abstractmethod
    def _get_trust_building_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция для построения доверия"""
        pass

    @abstractmethod
    def _get_project_inquiry_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция для выяснения о проектах"""
        pass

    @abstractmethod
    def _get_interest_qualification_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция для квалификации интереса"""
        pass

    @abstractmethod
    def _get_presentation_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция для презентации"""
        pass

    @abstractmethod
    def _get_objection_handling_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция для обработки возражений"""
        pass

    @abstractmethod
    def _get_conversion_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция для конверсии"""
        pass

    @abstractmethod
    def _get_post_conversion_instruction(self, context: Dict[str, Any]) -> str:
        """Инструкция после конверсии"""
        pass

    def get_followup_message_template(self, followup_type: str, context: Dict[str, Any]) -> str:
        """Получение шаблона фолоуап сообщения"""
        templates = {
            "reminder": self._get_reminder_template(context),
            "value": self._get_value_template(context),
            "proof": self._get_proof_template(context),
            "final": self._get_final_template(context),
        }
        return templates.get(followup_type, "Привет! Не забыл про меня? 😊")

    @abstractmethod
    def _get_reminder_template(self, context: Dict[str, Any]) -> str:
        """Шаблон напоминания"""
        pass

    @abstractmethod
    def _get_value_template(self, context: Dict[str, Any]) -> str:
        """Шаблон ценности"""
        pass

    @abstractmethod
    def _get_proof_template(self, context: Dict[str, Any]) -> str:
        """Шаблон социального доказательства"""
        pass

    @abstractmethod
    def _get_final_template(self, context: Dict[str, Any]) -> str:
        """Финальный шаблон"""
        pass

    def analyze_user_message(self, message: str, conversation_history: List[Dict]) -> Dict[str, Any]:
        """Анализ сообщения пользователя"""
        # Базовый анализ, может быть переопределен в наследниках
        analysis = {
            "sentiment": self._detect_sentiment(message),
            "interest_level": self._detect_interest_level(message),
            "objections": self._detect_objections(message),
            "questions": self._detect_questions(message),
            "project_mentions": self._detect_project_mentions(message),
        }
        return analysis

    def _detect_sentiment(self, message: str) -> str:
        """Определение настроения сообщения"""
        positive_words = ["хорошо", "отлично", "интересно", "круто", "нравится", "да", "ок"]
        negative_words = ["плохо", "не верю", "скам", "нет", "не хочу", "не интересно"]

        message_lower = message.lower()
        positive_count = sum(1 for word in positive_words if word in message_lower)
        negative_count = sum(1 for word in negative_words if word in message_lower)

        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"

    def _detect_interest_level(self, message: str) -> str:
        """Определение уровня заинтересованности"""
        high_interest = ["расскажи", "как", "сколько", "хочу", "интересно", "давай", "можно"]
        low_interest = ["не знаю", "может быть", "посмотрим", "подумаю"]

        message_lower = message.lower()

        if any(word in message_lower for word in high_interest):
            return "high"
        elif any(word in message_lower for word in low_interest):
            return "low"
        else:
            return "medium"

    def _detect_objections(self, message: str) -> List[str]:
        """Определение возражений"""
        objections = []
        message_lower = message.lower()

        if any(word in message_lower for word in ["скам", "обман", "развод"]):
            objections.append("trust_issue")
        if any(word in message_lower for word in ["нет денег", "дорого", "много"]):
            objections.append("financial")
        if any(word in message_lower for word in ["не понимаю", "сложно", "не разбираюсь"]):
            objections.append("complexity")
        if any(word in message_lower for word in ["нет времени", "некогда", "занят"]):
            objections.append("time")

        return objections

    def _detect_questions(self, message: str) -> List[str]:
        """Определение типов вопросов"""
        questions = []
        message_lower = message.lower()

        if any(word in message_lower for word in ["как", "каким образом"]):
            questions.append("how")
        if any(word in message_lower for word in ["сколько", "какая сумма"]):
            questions.append("amount")
        if any(word in message_lower for word in ["когда", "через сколько"]):
            questions.append("timing")
        if any(word in message_lower for word in ["что это", "что за"]):
            questions.append("what")
        if any(word in message_lower for word in ["безопасно", "надежно", "риски"]):
            questions.append("safety")

        return questions

    def _detect_project_mentions(self, message: str) -> List[str]:
        """Определение упоминаний проектов"""
        project_keywords = ["проект", "платформа", "бот", "инвестиции", "заработок", "доход"]
        mentions = []
        message_lower = message.lower()

        for keyword in project_keywords:
            if keyword in message_lower:
                mentions.append(keyword)

        return mentions