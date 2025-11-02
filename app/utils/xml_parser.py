"""
XML Parser for Figure Skating Tournament Results
Handles parsing of XML files containing tournament data
"""

# ✅ Используем defusedxml для защиты от XXE атак
try:
    import defusedxml.ElementTree as ET
except ImportError:
    # Fallback если defusedxml не установлен
    import xml.etree.ElementTree as ET
    import warnings
    warnings.warn("defusedxml not installed - XXE protection disabled", UserWarning)
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class TournamentXMLParser:
    """Parser for tournament XML files"""
    
    def __init__(self):
        self.event_data = {}
        self.categories = []
        self.athletes = []
        self.errors = []
    
    def parse_file(self, file_path: str) -> Dict:
        """
        Parse XML file and return structured data
        
        Args:
            file_path: Path to XML file
            
        Returns:
            Dict containing parsed data and metadata
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # Reset data
            self.event_data = {}
            self.categories = []
            self.athletes = []
            self.errors = []
            
            # Parse event information
            self._parse_event(root)
            
            # Parse categories and athletes
            self._parse_categories(root)
            
            return {
                'event': self.event_data,
                'categories': self.categories,
                'athletes': self.athletes,
                'errors': self.errors,
                'success': len(self.errors) == 0
            }
            
        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")
            return {
                'success': False,
                'errors': [f'Ошибка парсинга XML: {str(e)}']
            }
        except Exception as e:
            logger.error(f"Unexpected error parsing XML: {e}")
            return {
                'success': False,
                'errors': [f'Неожиданная ошибка: {str(e)}']
            }
    
    def _parse_event(self, root: ET.Element):
        """Parse event information from XML root"""
        event_elem = root.find('Event')
        if event_elem is None:
            self.errors.append('Элемент Event не найден в XML')
            return
        
        # Parse event name
        name_elem = event_elem.find('EVT_NAME')
        if name_elem is not None and name_elem.text:
            self.event_data['name'] = name_elem.text.strip()
        else:
            self.errors.append('Название турнира не найдено')
        
        # Parse event place
        place_elem = event_elem.find('EVT_PLACE')
        if place_elem is not None and place_elem.text:
            self.event_data['place'] = place_elem.text.strip()
        
        # Parse start date
        start_date_elem = event_elem.find('EVT_BEGDAT')
        if start_date_elem is not None and start_date_elem.text:
            try:
                self.event_data['start_date'] = self._parse_date(start_date_elem.text.strip())
            except ValueError as e:
                self.errors.append(f'Неверный формат даты начала: {str(e)}')
        
        # Parse end date
        end_date_elem = event_elem.find('EVT_ENDDAT')
        if end_date_elem is not None and end_date_elem.text:
            try:
                self.event_data['end_date'] = self._parse_date(end_date_elem.text.strip())
            except ValueError as e:
                self.errors.append(f'Неверный формат даты окончания: {str(e)}')
    
    def _parse_categories(self, root: ET.Element):
        """Parse categories and athletes from XML"""
        categories = root.findall('Category')
        
        for cat_idx, category_elem in enumerate(categories):
            try:
                category_data = self._parse_category(category_elem)
                if category_data:
                    self.categories.append(category_data)
                    self._parse_athletes_in_category(category_elem, len(self.categories) - 1)
            except Exception as e:
                self.errors.append(f'Ошибка обработки категории {cat_idx + 1}: {str(e)}')
    
    def _parse_category(self, category_elem: ET.Element) -> Optional[Dict]:
        """Parse single category from XML element"""
        category_data = {}
        
        # Parse category name
        name_elem = category_elem.find('CAT_NAME')
        if name_elem is not None and name_elem.text:
            category_data['name'] = name_elem.text.strip()
        else:
            self.errors.append('Название категории не найдено')
            return None
        
        # Parse category gender
        gender_elem = category_elem.find('CAT_GENDER')
        if gender_elem is not None and gender_elem.text:
            category_data['gender'] = self._normalize_gender(gender_elem.text.strip())
        
        return category_data
    
    def _parse_athletes_in_category(self, category_elem: ET.Element, category_index: int):
        """Parse athletes in a specific category"""
        participants = category_elem.findall('Participant')
        
        for part_idx, participant_elem in enumerate(participants):
            try:
                athlete_data = self._parse_athlete(participant_elem, category_index)
                if athlete_data:
                    self.athletes.append(athlete_data)
            except Exception as e:
                self.errors.append(f'Ошибка обработки участника {part_idx + 1}: {str(e)}')
    
    def _parse_athlete(self, participant_elem: ET.Element, category_index: int) -> Optional[Dict]:
        """Parse single athlete from XML element"""
        person_elem = participant_elem.find('Person_Couple_Team')
        if person_elem is None:
            return None
        
        athlete_data = {
            'category_index': category_index
        }
        
        # Parse athlete name
        name_elem = person_elem.find('PCT_CNAME')
        if name_elem is not None and name_elem.text:
            athlete_name = name_elem.text.strip()
            
            # Handle pairs
            if '/' in athlete_name:
                names = athlete_name.split(' / ')
                if len(names) >= 2:
                    athlete_data['name'] = names[0].strip()
                    athlete_data['partner_name'] = names[1].strip()
                    athlete_data['is_pair'] = True
                else:
                    athlete_data['name'] = athlete_name
                    athlete_data['is_pair'] = False
            else:
                athlete_data['name'] = athlete_name
                athlete_data['is_pair'] = False
        else:
            return None
        
        # Parse birth date
        birth_elem = person_elem.find('PCT_BDAY')
        if birth_elem is not None and birth_elem.text:
            try:
                athlete_data['birth_date'] = self._parse_date(birth_elem.text.strip())
            except ValueError as e:
                self.errors.append(f'Неверный формат даты рождения для {athlete_data["name"]}: {str(e)}')
        
        # Parse gender
        gender_elem = person_elem.find('PCT_GENDER')
        if gender_elem is not None and gender_elem.text:
            athlete_data['gender'] = self._normalize_gender(gender_elem.text.strip())
        
        # Parse club
        club_elem = person_elem.find('Club')
        if club_elem is not None:
            club_name_elem = club_elem.find('CLB_NAME')
            if club_name_elem is not None and club_name_elem.text:
                athlete_data['club_name'] = club_name_elem.text.strip()
        
        return athlete_data
    
    def _parse_date(self, date_str: str) -> datetime:
        """
        Parse date from YYYYMMDD format
        
        Args:
            date_str: Date string in YYYYMMDD format
            
        Returns:
            datetime object
            
        Raises:
            ValueError: If date format is invalid
        """
        if not date_str or len(date_str) != 8:
            raise ValueError(f'Неверный формат даты: {date_str}')
        
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except ValueError:
            raise ValueError(f'Неверный формат даты: {date_str}')
    
    def _normalize_gender(self, gender: str) -> str:
        """
        Normalize gender string to standard format
        
        Args:
            gender: Gender string from XML
            
        Returns:
            Normalized gender ('M', 'F', or 'MIXED')
        """
        if not gender:
            return None
        
        gender_upper = gender.upper()
        
        if gender_upper in ['M', 'MALE', 'М', 'МУЖ', 'МУЖСКОЙ']:
            return 'M'
        elif gender_upper in ['F', 'FEMALE', 'Ж', 'ЖЕН', 'ЖЕНСКИЙ']:
            return 'F'
        elif gender_upper in ['MIXED', 'СМЕШАННЫЙ', 'ПАРЫ']:
            return 'MIXED'
        else:
            # Default to MIXED for unknown values
            return 'MIXED'
    
    def validate_data(self) -> List[str]:
        """
        Validate parsed data for completeness and consistency
        
        Returns:
            List of validation errors
        """
        validation_errors = []
        
        # Validate event data
        if not self.event_data.get('name'):
            validation_errors.append('Название турнира обязательно')
        
        if not self.event_data.get('start_date'):
            validation_errors.append('Дата начала турнира обязательна')
        
        # Validate categories
        if not self.categories:
            validation_errors.append('Не найдено ни одной категории')
        
        # Validate athletes
        if not self.athletes:
            validation_errors.append('Не найдено ни одного спортсмена')
        
        # Check for duplicate athlete names within categories
        for category_index, category in enumerate(self.categories):
            athletes_in_category = [
                athlete for athlete in self.athletes 
                if athlete['category_index'] == category_index
            ]
            
            names = [athlete['name'] for athlete in athletes_in_category]
            if len(names) != len(set(names)):
                validation_errors.append(f'Найдены дублирующиеся имена в категории "{category["name"]}"')
        
        return validation_errors

def parse_tournament_xml(file_path: str) -> Dict:
    """
    Convenience function to parse tournament XML file
    
    Args:
        file_path: Path to XML file
        
    Returns:
        Dict containing parsed data and metadata
    """
    parser = TournamentXMLParser()
    result = parser.parse_file(file_path)
    
    # Add validation if parsing was successful
    if result['success']:
        validation_errors = parser.validate_data()
        result['validation_errors'] = validation_errors
        result['success'] = len(validation_errors) == 0
    
    return result
