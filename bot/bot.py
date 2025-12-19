import os
import logging
import json
import re
import time
import random
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import Flask, request, jsonify, Response
from telegram import (
    Bot, Update, ParseMode, ReplyKeyboardMarkup, 
    KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup,
    InlineKeyboardButton, ChatPermissions
)
from telegram.ext import (
    Dispatcher, CommandHandler, MessageHandler, 
    Filters, CallbackContext, CallbackQueryHandler,
    ConversationHandler, Updater
)
from telegram.utils.helpers import escape_markdown
import threading

# ==================== CONFIGURATION ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment variables
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '123').strip()
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID', '').strip()
ALPHAVANTAGE_API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY', '').strip()
COMMUNITY_GROUP_ID = os.environ.get('COMMUNITY_GROUP_ID', '').strip()
PAYMENT_GROUP_ID = os.environ.get('PAYMENT_GROUP_ID', '').strip()
DEFAULT_EXCHANGE = os.environ.get('DEFAULT_EXCHANGE', 'NYSE').strip()

BOT_USERNAME = None
BOT_ID = None
BOT_NAME = None
PORT = int(os.environ.get('PORT', 8080))

# Validation
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")

if not WEBHOOK_URL:
    logger.warning("⚠️ WEBHOOK_URL not set, webhook will not be configured")

# Bot initialization
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=4)

# Get bot info dynamically
try:
    bot_info = bot.get_me()
    BOT_USERNAME = bot_info.username
    BOT_ID = bot_info.id
    BOT_NAME = bot_info.first_name
    logger.info(f"🤖 Bot loaded: @{BOT_USERNAME} (ID: {BOT_ID}, Name: {BOT_NAME})")
except Exception as e:
    logger.error(f"Failed to get bot info: {e}")
    BOT_USERNAME = os.environ.get('BOT_USERNAME', 'unknown_bot')
    BOT_ID = os.environ.get('BOT_ID', 'unknown')
    BOT_NAME = os.environ.get('BOT_NAME', 'Telegram Bot')

# Storage files
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
BROADCASTS_FILE = os.path.join(DATA_DIR, "broadcasts.json")
GROUPS_FILE = os.path.join(DATA_DIR, "groups.json")
STOCKS_FILE = os.path.join(DATA_DIR, "stocks.json")
ECONOMIC_FILE = os.path.join(DATA_DIR, "economic_events.json")
QUIZ_FILE = os.path.join(DATA_DIR, "quiz_scores.json")
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== ENHANCED STORAGE FUNCTIONS ====================
def load_json(filepath, default=None):
    """Load JSON file, return default if file doesn't exist"""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
    return default

def save_json(filepath, data):
    """Save data to JSON file"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")
        return False

# Load existing data
users_db = load_json(USERS_FILE, [])
messages_db = load_json(MESSAGES_FILE, [])
broadcasts_db = load_json(BROADCASTS_FILE, [])
groups_db = load_json(GROUPS_FILE, [])
stocks_db = load_json(STOCKS_FILE, {})
economic_events_db = load_json(ECONOMIC_FILE, [])
quiz_scores_db = load_json(QUIZ_FILE, {})
tasks_db = load_json(TASKS_FILE, [])

# ==================== ENHANCED STATS SYSTEM ====================
class BotStatistics:
    """Enhanced statistics tracking system"""
    def __init__(self):
        self.stats = {
            'start_count': 0,
            'message_count': 0,
            'commands_count': {},
            'users': set(),
            'active_users': set(),
            'groups': set(),
            'start_time': datetime.now().isoformat(),
            'last_update': None,
            'bot_id': BOT_ID,
            'bot_username': BOT_USERNAME,
            'uptime_seconds': 0,
            'daily_active_users': {},
            'hourly_activity': {},
            'features_used': {},
            'errors_count': 0
        }
        
        # Load from existing data
        self._load_from_storage()
        
    def _load_from_storage(self):
        """Load statistics from existing storage"""
        for user in users_db:
            if 'user_id' in user:
                self.stats['users'].add(user['user_id'])
                self.stats['message_count'] += user.get('message_count', 0)
                if user.get('first_seen'):
                    self.stats['start_count'] += 1
                    
                # Check if active in last 24 hours
                if user.get('last_seen'):
                    last_seen = datetime.fromisoformat(user['last_seen'])
                    if (datetime.now() - last_seen).days < 1:
                        self.stats['active_users'].add(user['user_id'])

        for group in groups_db:
            if 'chat_id' in group:
                self.stats['groups'].add(group['chat_id'])
                
    def update(self, update_type: str, data: Dict = None):
        """Update statistics"""
        self.stats['last_update'] = datetime.now().isoformat()
        self.stats['uptime_seconds'] = (datetime.now() - 
            datetime.fromisoformat(self.stats['start_time'])).total_seconds()
        
        if update_type == 'message':
            self.stats['message_count'] += 1
            
            # Track hourly activity
            hour = datetime.now().hour
            self.stats['hourly_activity'][hour] = \
                self.stats['hourly_activity'].get(hour, 0) + 1
                
        elif update_type == 'command':
            cmd = data.get('command', 'unknown')
            self.stats['commands_count'][cmd] = \
                self.stats['commands_count'].get(cmd, 0) + 1
                
        elif update_type == 'user_active':
            user_id = data.get('user_id')
            if user_id:
                self.stats['active_users'].add(user_id)
                
        elif update_type == 'feature_used':
            feature = data.get('feature', 'unknown')
            self.stats['features_used'][feature] = \
                self.stats['features_used'].get(feature, 0) + 1
                
        elif update_type == 'error':
            self.stats['errors_count'] += 1
            
    def get_summary(self) -> Dict:
        """Get statistics summary"""
        return {
            'uptime': str(timedelta(seconds=int(self.stats['uptime_seconds']))),
            'total_messages': self.stats['message_count'],
            'total_users': len(self.stats['users']),
            'active_users': len(self.stats['active_users']),
            'total_groups': len(self.stats['groups']),
            'start_count': self.stats['start_count'],
            'commands_count': sum(self.stats['commands_count'].values()),
            'top_commands': sorted(
                self.stats['commands_count'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5],
            'errors_count': self.stats['errors_count']
        }
    
    def get_hourly_activity(self) -> List:
        """Get hourly activity distribution"""
        activity = []
        for hour in range(24):
            activity.append({
                'hour': hour,
                'count': self.stats['hourly_activity'].get(hour, 0)
            })
        return activity

bot_stats = BotStatistics()

# ==================== ADVANCED EVOLUTIONARY DNA SYSTEM ====================
class AdvancedBotDNA:
    """Enhanced evolutionary DNA system with machine learning patterns"""
    
    def __init__(self):
        self.dna_path = os.path.join(DATA_DIR, "evolution", "dna_v2.json")
        self.modules_path = os.path.join(DATA_DIR, "evolution", "modules")
        self.archive_path = os.path.join(DATA_DIR, "evolution", "archive")
        self.mutations_path = os.path.join(DATA_DIR, "evolution", "mutations")
        self.knowledge_path = os.path.join(DATA_DIR, "knowledge")
        self.learning_path = os.path.join(DATA_DIR, "learning")
        
        # Create directories
        for path in [self.modules_path, self.archive_path, 
                    self.mutations_path, self.knowledge_path,
                    self.learning_path]:
            os.makedirs(path, exist_ok=True)
        
        # Load or create DNA
        self.dna = self._load_or_create_dna()
        self.learning_data = self._load_learning_data()
        
    def _load_or_create_dna(self):
        """Load or create advanced DNA structure"""
        if os.path.exists(self.dna_path):
            dna = load_json(self.dna_path, {})
            logger.info(f"🧬 Loaded existing DNA: Generation {dna.get('generation', 1)}")
            return dna
        
        # Advanced DNA structure
        base_dna = {
            "bot_id": BOT_ID,
            "bot_name": BOT_NAME,
            "creation_date": datetime.now().isoformat(),
            "last_evolution": datetime.now().isoformat(),
            "lineage": ["primordial_bot_v1", "advanced_evolution_v2"],
            "generation": 2,
            "modules": {},
            "mutations": [],
            "crossovers": [],
            "fitness_score": 85,
            "adaptation_level": 0.7,
            "learning_rate": 0.1,
            "memory": {
                "lessons_learned": [],
                "patterns_discovered": [],
                "optimizations_applied": [],
                "user_preferences": {},
                "performance_metrics": {}
            },
            "capabilities": {
                "nlp": False,
                "prediction": False,
                "automation": True,
                "integration": True,
                "learning": True
            },
            "traits": {
                "responsiveness": 0.9,
                "reliability": 0.95,
                "innovation": 0.75,
                "efficiency": 0.85
            }
        }
        
        save_json(self.dna_path, base_dna)
        logger.info(f"🧬 Created advanced DNA for {BOT_NAME}")
        return base_dna
    
    def _load_learning_data(self):
        """Load machine learning data"""
        learning_file = os.path.join(self.learning_path, "patterns.json")
        return load_json(learning_file, {
            "user_patterns": {},
            "command_patterns": {},
            "time_patterns": {},
            "conversation_patterns": {},
            "learning_models": {}
        })
    
    def _save_dna(self):
        """Save DNA to file"""
        return save_json(self.dna_path, self.dna)
    
    def _save_learning_data(self):
        """Save learning data"""
        learning_file = os.path.join(self.learning_path, "patterns.json")
        return save_json(learning_file, self.learning_data)
    
    def _analyze_user_pattern(self, user_id: int, command: str, context: Dict):
        """Analyze user behavior patterns"""
        if str(user_id) not in self.learning_data["user_patterns"]:
            self.learning_data["user_patterns"][str(user_id)] = {
                "command_frequency": {},
                "preferred_features": [],
                "activity_times": [],
                "interaction_style": "neutral",
                "trust_level": 0.5
            }
        
        user_pattern = self.learning_data["user_patterns"][str(user_id)]
        user_pattern["command_frequency"][command] = \
            user_pattern["command_frequency"].get(command, 0) + 1
        
        # Update activity time
        hour = datetime.now().hour
        if hour not in user_pattern["activity_times"]:
            user_pattern["activity_times"].append(hour)
        
        self._save_learning_data()
        
    def register_advanced_module(self, module_name: str, module_type: str, 
                                functions: List[str] = None, 
                                dependencies: List[str] = None,
                                complexity: int = 1):
        """Register advanced module with dependencies"""
        module_id = f"mod_{int(time.time())}_{len(self.dna['modules'])}"
        
        module_data = {
            "id": module_id,
            "name": module_name,
            "type": module_type,
            "complexity": complexity,
            "dependencies": dependencies or [],
            "birth_date": datetime.now().isoformat(),
            "functions": functions or [],
            "status": "active",
            "version": "1.0",
            "performance": {
                "calls": 0,
                "success_rate": 1.0,
                "avg_response_time": 0,
                "last_used": datetime.now().isoformat()
            },
            "metadata": {
                "author": "evolution_system",
                "tags": ["auto_generated"],
                "description": f"Auto-generated {module_type} module"
            }
        }
        
        self.dna["modules"][module_id] = module_data
        self.dna["generation"] = max(self.dna.get("generation", 1), 
                                    self._calculate_generation(module_data))
        
        # Save module to separate file
        module_file = os.path.join(self.modules_path, f"{module_id}.json")
        save_json(module_file, module_data)
        
        logger.info(f"🧬 Registered advanced module: {module_name} ({module_id})")
        self._save_dna()
        
        return module_id
    
    def _calculate_generation(self, module_data: Dict) -> int:
        """Calculate generation based on module complexity and dependencies"""
        base_gen = len(module_data.get("dependencies", [])) + 2
        complexity_bonus = min(module_data.get("complexity", 1) // 2, 3)
        return base_gen + complexity_bonus
    
    def record_intelligent_mutation(self, module_id: str, mutation_type: str, 
                                   description: str, impact: str = "medium",
                                   trigger: str = "auto_detection",
                                   confidence: float = 0.8):
        """Record intelligent mutation with confidence scoring"""
        mutation_id = f"mut_{int(time.time())}_{random.randint(1000, 9999)}"
        
        mutation = {
            "id": mutation_id,
            "module_id": module_id,
            "type": mutation_type,
            "subtype": self._classify_mutation(mutation_type, description),
            "description": description,
            "impact": impact,
            "trigger": trigger,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
            "environment": {
                "bot_version": self.dna.get("generation", 1),
                "active_users": len(bot_stats.stats['active_users']),
                "system_load": self._calculate_system_load()
            },
            "analysis": {
                "before_performance": self.dna["modules"].get(module_id, {}).get("performance", {}),
                "expected_improvement": self._calculate_expected_improvement(impact),
                "risk_level": self._calculate_risk_level(mutation_type, impact)
            }
        }
        
        # Save mutation
        mutation_file = os.path.join(self.mutations_path, f"{mutation_id}.json")
        save_json(mutation_file, mutation)
        
        # Add to DNA
        self.dna["mutations"].append({
            "id": mutation_id,
            "module_id": module_id,
            "type": mutation_type,
            "timestamp": mutation["timestamp"],
            "impact": impact,
            "confidence": confidence
        })
        
        # Update fitness score
        self._update_advanced_fitness_score(mutation_type, impact, confidence)
        
        # Update module performance prediction
        self._update_module_performance_prediction(module_id, mutation)
        
        self._save_dna()
        self._log_intelligent_growth(mutation_type, module_id, confidence)
        
        return mutation_id
    
    def _classify_mutation(self, mutation_type: str, description: str) -> str:
        """Classify mutation type"""
        description_lower = description.lower()
        
        if "optimiz" in description_lower:
            return "performance_optimization"
        elif "bug" in description_lower or "fix" in description_lower:
            return "bug_fix"
        elif "feature" in description_lower or "add" in description_lower:
            return "feature_addition"
        elif "security" in description_lower:
            return "security_enhancement"
        elif "integration" in description_lower:
            return "integration"
        else:
            return "general_improvement"
    
    def _calculate_system_load(self) -> float:
        """Calculate current system load"""
        total_messages = bot_stats.stats['message_count']
        active_users = len(bot_stats.stats['active_users'])
        
        if total_messages == 0:
            return 0.0
        
        # Simple load calculation based on recent activity
        recent_hour = datetime.now().hour
        hourly_load = bot_stats.stats['hourly_activity'].get(recent_hour, 0)
        
        return min(hourly_load / 100.0, 1.0)
    
    def _calculate_expected_improvement(self, impact: str) -> float:
        """Calculate expected improvement from mutation"""
        impact_scores = {
            "low": 0.1,
            "medium": 0.3,
            "high": 0.6,
            "critical": 0.9
        }
        return impact_scores.get(impact, 0.2)
    
    def _calculate_risk_level(self, mutation_type: str, impact: str) -> str:
        """Calculate risk level of mutation"""
        if impact == "critical" and mutation_type in ["core_change", "integration"]:
            return "high"
        elif impact in ["high", "critical"]:
            return "medium"
        else:
            return "low"
    
    def _update_advanced_fitness_score(self, mutation_type: str, impact: str, confidence: float):
        """Update fitness score with advanced calculation"""
        impact_weights = {
            "low": 1,
            "medium": 3,
            "high": 7,
            "critical": 15
        }
        
        type_weights = {
            "bug_fix": 2,
            "optimization": 1.5,
            "feature_add": 3,
            "security_enhancement": 4,
            "integration": 3,
            "core_change": 5
        }
        
        base_increase = impact_weights.get(impact, 1) * type_weights.get(mutation_type, 1)
        confidence_multiplier = 0.5 + (confidence * 0.5)  # 0.5-1.0 range
        score_increase = base_increase * confidence_multiplier
        
        # Cap at 100
        new_score = min(100, self.dna.get("fitness_score", 0) + score_increase)
        
        # Calculate adaptation level
        if new_score > self.dna.get("fitness_score", 0):
            improvement_ratio = score_increase / 100.0
            self.dna["adaptation_level"] = min(1.0, 
                self.dna.get("adaptation_level", 0) + (improvement_ratio * 0.1))
        
        self.dna["fitness_score"] = new_score
        
        # Update traits based on mutations
        self._update_traits(mutation_type, impact)
    
    def _update_traits(self, mutation_type: str, impact: str):
        """Update bot traits based on mutations"""
        traits = self.dna.get("traits", {})
        
        if mutation_type == "optimization":
            traits["efficiency"] = min(1.0, traits.get("efficiency", 0.8) + 0.05)
        elif mutation_type == "feature_add":
            traits["innovation"] = min(1.0, traits.get("innovation", 0.7) + 0.03)
        elif mutation_type == "bug_fix":
            traits["reliability"] = min(1.0, traits.get("reliability", 0.9) + 0.02)
        
        self.dna["traits"] = traits
    
    def _update_module_performance_prediction(self, module_id: str, mutation: Dict):
        """Update module performance prediction after mutation"""
        if module_id in self.dna["modules"]:
            module = self.dna["modules"][module_id]
            
            # Update performance metrics
            perf = module.get("performance", {})
            expected_improvement = mutation["analysis"]["expected_improvement"]
            
            # Adjust success rate prediction
            current_success = perf.get("success_rate", 1.0)
            if mutation["impact"] in ["high", "critical"]:
                new_success = min(1.0, current_success + (expected_improvement * 0.1))
                perf["success_rate"] = new_success
            
            module["performance"] = perf
    
    def _log_intelligent_growth(self, mutation_type: str, module_id: str, confidence: float):
        """Log intelligent growth event"""
        emoji = "🧠" if confidence > 0.7 else "⚡" if confidence > 0.4 else "🌱"
        logger.info(f"{emoji} Intelligent {mutation_type} on {module_id} "
                   f"(confidence: {confidence:.2f})")
    
    def analyze_and_evolve(self, pattern_data: Dict = None):
        """Analyze patterns and evolve intelligently"""
        if not pattern_data:
            pattern_data = self._collect_patterns()
        
        # Analyze patterns
        analysis = self._analyze_patterns(pattern_data)
        
        if analysis["should_evolve"]:
            evolution_plan = self._create_evolution_plan(analysis)
            
            # Execute evolution plan
            results = []
            for step in evolution_plan["steps"]:
                result = self._execute_evolution_step(step)
                results.append(result)
            
            # Record evolution event
            self._record_evolution_event(evolution_plan, results)
            
            return {
                "success": True,
                "evolution_id": evolution_plan["id"],
                "steps_executed": len(results),
                "new_modules": [r for r in results if r.get("module_id")]
            }
        
        return {"success": False, "reason": "No evolution needed"}
    
    def _collect_patterns(self) -> Dict:
        """Collect patterns from system data"""
        patterns = {
            "user_behavior": {},
            "system_performance": {},
            "feature_usage": {},
            "error_patterns": {}
        }
        
        # Analyze user behavior
        for user in users_db[-100:]:  # Last 100 users
            user_id = user.get('user_id')
            if user_id:
                patterns["user_behavior"][str(user_id)] = {
                    "message_count": user.get('message_count', 0),
                    "last_active": user.get('last_seen'),
                    "preferred_commands": self._analyze_user_commands(user_id)
                }
        
        # System performance patterns
        patterns["system_performance"] = {
            "uptime": bot_stats.stats['uptime_seconds'],
            "message_rate": bot_stats.stats['message_count'] / 
                          max(1, bot_stats.stats['uptime_seconds'] / 3600),
            "active_user_ratio": len(bot_stats.stats['active_users']) / 
                               max(1, len(bot_stats.stats['users']))
        }
        
        return patterns
    
    def _analyze_user_commands(self, user_id: int) -> Dict:
        """Analyze user's command usage patterns"""
        user_messages = [m for m in messages_db[-1000:] 
                        if m.get('user_id') == user_id]
        
        command_counts = {}
        for msg in user_messages:
            cmd = msg.get('command')
            if cmd and cmd not in ['text', 'unknown']:
                command_counts[cmd] = command_counts.get(cmd, 0) + 1
        
        return dict(sorted(command_counts.items(), 
                          key=lambda x: x[1], 
                          reverse=True)[:5])
    
    def _analyze_patterns(self, patterns: Dict) -> Dict:
        """Analyze collected patterns"""
        analysis = {
            "should_evolve": False,
            "evolution_type": None,
            "confidence": 0.0,
            "reasons": []
        }
        
        # Check for performance issues
        msg_rate = patterns["system_performance"].get("message_rate", 0)
        if msg_rate > 50:  # High message rate
            analysis["should_evolve"] = True
            analysis["evolution_type"] = "performance_optimization"
            analysis["confidence"] += 0.3
            analysis["reasons"].append(f"High message rate: {msg_rate:.1f}/hour")
        
        # Check for feature usage patterns
        if bot_stats.stats.get('features_used'):
            top_features = sorted(bot_stats.stats['features_used'].items(),
                                key=lambda x: x[1], reverse=True)[:3]
            
            for feature, count in top_features:
                if count > 100:  # Very popular feature
                    analysis["should_evolve"] = True
                    analysis["evolution_type"] = "feature_enhancement"
                    analysis["confidence"] += 0.2
                    analysis["reasons"].append(
                        f"Popular feature '{feature}' used {count} times"
                    )
        
        # Check for error patterns
        if bot_stats.stats['errors_count'] > 10:
            analysis["should_evolve"] = True
            analysis["evolution_type"] = "stability_improvement"
            analysis["confidence"] += 0.4
            analysis["reasons"].append(
                f"High error count: {bot_stats.stats['errors_count']}"
            )
        
        analysis["confidence"] = min(1.0, analysis["confidence"])
        
        return analysis
    
    def _create_evolution_plan(self, analysis: Dict) -> Dict:
        """Create evolution plan based on analysis"""
        plan_id = f"evo_{int(time.time())}_{random.randint(1000, 9999)}"
        
        plan = {
            "id": plan_id,
            "type": analysis["evolution_type"],
            "confidence": analysis["confidence"],
            "reasons": analysis["reasons"],
            "created": datetime.now().isoformat(),
            "status": "pending",
            "steps": []
        }
        
        # Define evolution steps based on type
        if analysis["evolution_type"] == "performance_optimization":
            plan["steps"] = [
                {
                    "action": "create_module",
                    "module_type": "performance",
                    "name": f"auto_perf_opt_{int(time.time())}",
                    "functions": ["optimize_response", "cache_management"],
                    "priority": "high"
                },
                {
                    "action": "mutate",
                    "module_id": "core_bot",
                    "mutation_type": "optimization",
                    "description": "Performance optimization for high load"
                }
            ]
        elif analysis["evolution_type"] == "feature_enhancement":
            plan["steps"] = [
                {
                    "action": "enhance_module",
                    "module_type": "feature_core",
                    "description": "Add advanced features based on usage"
                }
            ]
        
        return plan
    
    def _execute_evolution_step(self, step: Dict) -> Dict:
        """Execute single evolution step"""
        result = {"step": step, "success": False}
        
        try:
            if step["action"] == "create_module":
                module_id = self.register_advanced_module(
                    module_name=step["name"],
                    module_type=step["module_type"],
                    functions=step.get("functions", []),
                    complexity=2
                )
                result["module_id"] = module_id
                result["success"] = True
                
            elif step["action"] == "mutate":
                mutation_id = self.record_intelligent_mutation(
                    module_id=step["module_id"],
                    mutation_type=step["mutation_type"],
                    description=step["description"],
                    impact="high",
                    confidence=0.7
                )
                result["mutation_id"] = mutation_id
                result["success"] = True
            
            elif step["action"] == "enhance_module":
                # Simple enhancement
                result["success"] = True
                result["message"] = "Module enhancement scheduled"
        
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _record_evolution_event(self, plan: Dict, results: List[Dict]):
        """Record evolution event in knowledge base"""
        evolution_event = {
            "id": plan["id"],
            "type": plan["type"],
            "timestamp": datetime.now().isoformat(),
            "confidence": plan["confidence"],
            "reasons": plan["reasons"],
            "results": results,
            "metrics": {
                "before_fitness": self.dna.get("fitness_score"),
                "active_modules": len(self.dna.get("modules", {})),
                "user_count": len(bot_stats.stats['users'])
            }
        }
        
        # Save to knowledge base
        knowledge_file = os.path.join(self.knowledge_path, "evolution_history.json")
        history = load_json(knowledge_file, [])
        history.append(evolution_event)
        save_json(knowledge_file, history)
        
        # Update DNA
        self.dna["last_evolution"] = datetime.now().isoformat()
        
        # Add to memory
        self.dna["memory"]["lessons_learned"].append({
            "evolution_id": plan["id"],
            "type": plan["type"],
            "timestamp": datetime.now().isoformat()
        })
        
        self._save_dna()
        logger.info(f"🧬 Evolution {plan['id']} completed: {plan['type']}")
    
    def get_evolution_report(self) -> Dict:
        """Get comprehensive evolution report"""
        report = {
            "dna_info": {
                "generation": self.dna.get("generation", 1),
                "fitness_score": self.dna.get("fitness_score", 0),
                "adaptation_level": self.dna.get("adaptation_level", 0),
                "total_mutations": len(self.dna.get("mutations", [])),
                "total_modules": len(self.dna.get("modules", {})),
                "last_evolution": self.dna.get("last_evolution")
            },
            "traits": self.dna.get("traits", {}),
            "capabilities": self.dna.get("capabilities", {}),
            "recent_mutations": self.dna.get("mutations", [])[-5:],
            "active_modules": [
                {"id": k, "name": v.get("name"), "type": v.get("type")}
                for k, v in self.dna.get("modules", {}).items()
                if v.get("status") == "active"
            ][-10:],
            "learning_insights": {
                "user_patterns_count": len(self.learning_data.get("user_patterns", {})),
                "command_patterns_count": len(self.learning_data.get("command_patterns", {})),
                "total_learned_patterns": sum(
                    len(v) for v in self.learning_data.values() 
                    if isinstance(v, dict)
                )
            }
        }
        
        # Calculate evolution progress
        total_possible_score = 100
        progress_percent = (self.dna.get("fitness_score", 0) / total_possible_score) * 100
        report["progress"] = {
            "percent": progress_percent,
            "level": self._get_evolution_level(progress_percent),
            "next_milestone": self._get_next_milestone(progress_percent)
        }
        
        return report
    
    def _get_evolution_level(self, progress: float) -> str:
        """Get evolution level based on progress"""
        if progress >= 90:
            return "Transcendent"
        elif progress >= 75:
            return "Advanced"
        elif progress >= 50:
            return "Intermediate"
        elif progress >= 25:
            return "Developing"
        else:
            return "Primordial"
    
    def _get_next_milestone(self, progress: float) -> Dict:
        """Get next evolution milestone"""
        milestones = [25, 50, 75, 90, 95, 100]
        
        for milestone in milestones:
            if progress < milestone:
                return {
                    "target": milestone,
                    "points_needed": milestone - progress,
                    "estimated_mutations": int((milestone - progress) / 5)
                }
        
        return {"target": 100, "points_needed": 0, "estimated_mutations": 0}

# Initialize advanced DNA system
advanced_dna = AdvancedBotDNA()

# ==================== FINANCIAL MODULES ====================
class FinancialAssistant:
    """Financial assistant module for stock and economic data"""
    
    def __init__(self):
        self.api_key = ALPHAVANTAGE_API_KEY
        self.base_url = "https://www.alphavantage.co/query"
        
        # Register with DNA
        self.module_id = advanced_dna.register_advanced_module(
            module_name="financial_assistant",
            module_type="financial",
            functions=[
                "get_stock_price", 
                "get_stock_analysis",
                "get_economic_events",
                "get_exchange_rates",
                "portfolio_tracking"
            ],
            dependencies=["core_bot", "integration"],
            complexity=3
        )
        
        # Record initial mutation
        advanced_dna.record_intelligent_mutation(
            module_id=self.module_id,
            mutation_type="feature_add",
            description="Financial assistant module with Alpha Vantage integration",
            impact="high",
            trigger="manual_creation",
            confidence=0.9
        )
    
    def get_stock_price(self, symbol: str) -> Dict:
        """Get current stock price"""
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            
            if "Global Quote" in data:
                quote = data["Global Quote"]
                return {
                    "symbol": symbol,
                    "price": quote.get("05. price"),
                    "change": quote.get("09. change"),
                    "change_percent": quote.get("10. change percent"),
                    "volume": quote.get("06. volume"),
                    "latest_trading_day": quote.get("07. latest trading day"),
                    "success": True
                }
            else:
                return {"success": False, "error": "Symbol not found"}
                
        except Exception as e:
            logger.error(f"Error fetching stock price: {e}")
            return {"success": False, "error": str(e)}
    
    def get_stock_analysis(self, symbol: str) -> Dict:
        """Get stock analysis and overview"""
        try:
            params = {
                "function": "OVERVIEW",
                "symbol": symbol,
                "apikey": self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            
            if data and "Symbol" in data:
                return {
                    "symbol": data.get("Symbol"),
                    "name": data.get("Name"),
                    "description": data.get("Description", "")[:500],
                    "sector": data.get("Sector"),
                    "industry": data.get("Industry"),
                    "market_cap": data.get("MarketCapitalization"),
                    "pe_ratio": data.get("PERatio"),
                    "dividend_yield": data.get("DividendYield"),
                    "eps": data.get("EPS"),
                    "beta": data.get("Beta"),
                    "success": True
                }
            else:
                return {"success": False, "error": "Analysis not available"}
                
        except Exception as e:
            logger.error(f"Error fetching stock analysis: {e}")
            return {"success": False, "error": str(e)}
    
    def get_economic_calendar(self) -> List[Dict]:
        """Get upcoming economic events"""
        try:
            # This is a placeholder - Alpha Vantage doesn't have free economic calendar
            # In production, you'd use a different API
            events = economic_events_db or []
            
            # If no events in DB, create sample
            if not events:
                events = [
                    {
                        "event": "FOMC Meeting",
                        "date": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
                        "importance": "high",
                        "currency": "USD",
                        "description": "Federal Open Market Committee meeting"
                    },
                    {
                        "event": "GDP Release",
                        "date": (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"),
                        "importance": "medium",
                        "currency": "USD",
                        "description": "Gross Domestic Product quarterly report"
                    }
                ]
            
            return events
            
        except Exception as e:
            logger.error(f"Error fetching economic calendar: {e}")
            return []
    
    def get_exchange_rate(self, from_currency: str, to_currency: str) -> Dict:
        """Get currency exchange rate"""
        try:
            params = {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_currency,
                "to_currency": to_currency,
                "apikey": self.api_key
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            
            if "Realtime Currency Exchange Rate" in data:
                rate_data = data["Realtime Currency Exchange Rate"]
                return {
                    "from": rate_data.get("1. From_Currency Code"),
                    "to": rate_data.get("3. To_Currency Code"),
                    "rate": rate_data.get("5. Exchange Rate"),
                    "bid": rate_data.get("8. Bid Price"),
                    "ask": rate_data.get("9. Ask Price"),
                    "timestamp": rate_data.get("6. Last Refreshed"),
                    "success": True
                }
            else:
                return {"success": False, "error": "Exchange rate not available"}
                
        except Exception as e:
            logger.error(f"Error fetching exchange rate: {e}")
            return {"success": False, "error": str(e)}

# Initialize financial assistant
financial_assistant = FinancialAssistant()

# ==================== QUIZ & GAME SYSTEM ====================
class QuizGameSystem:
    """Quiz and game system for user engagement"""
    
    def __init__(self):
        self.quizzes = self._load_quizzes()
        self.active_games = {}
        self.module_id = advanced_dna.register_advanced_module(
            module_name="quiz_game_system",
            module_type="entertainment",
            functions=[
                "start_quiz",
                "answer_question",
                "get_leaderboard",
                "create_custom_quiz",
                "award_points"
            ],
            dependencies=["core_bot", "user_management"],
            complexity=2
        )
    
    def _load_quizzes(self) -> Dict:
        """Load quiz questions"""
        quizzes = {
            "trivia": [
                {
                    "question": "מהו הביטוי המתמטי של משפט פיתגורס?",
                    "options": ["a² + b² = c²", "E = mc²", "πr²", "F = ma"],
                    "correct": 0,
                    "points": 10
                },
                {
                    "question": "מי כתב את 'הנסיך הקטן'?",
                    "options": ["אנטואן דה סנט-אכזופרי", "מרק טוויין", "צ'ארלס דיקנס", "ויליאם שייקספיר"],
                    "correct": 0,
                    "points": 10
                },
                {
                    "question": "מהו היסוד הכימי עם הסמל Au?",
                    "options": ["זהב", "כסף", "ארסן", "אורניום"],
                    "correct": 0,
                    "points": 10
                }
            ],
            "tech": [
                {
                    "question": "באיזו שפה נכתב הלינוקס?",
                    "options": ["C", "Python", "Java", "C++"],
                    "correct": 0,
                    "points": 15
                },
                {
                    "question": "מהו HTTP?",
                    "options": ["פרוטוקול תקשורת", "שפת תכנות", "מסד נתונים", "מערכת הפעלה"],
                    "correct": 0,
                    "points": 15
                }
            ],
            "finance": [
                {
                    "question": "מהו ה-S&P 500?",
                    "options": ["מדד מניות אמריקאי", "סוג של קרן נאמנות", "ביטוח חיים", "סוג הלוואה"],
                    "correct": 0,
                    "points": 20
                },
                {
                    "question": "מהו ריבית?",
                    "options": ["עלות ההלוואה", "סוג מס", "דמי ניהול", "בונוס בנקאי"],
                    "correct": 0,
                    "points": 20
                }
            ]
        }
        return quizzes
    
    def start_quiz(self, user_id: int, quiz_type: str = "trivia") -> Dict:
        """Start a new quiz for user"""
        if quiz_type not in self.quizzes:
            return {"success": False, "error": "Quiz type not found"}
        
        quiz_questions = self.quizzes[quiz_type]
        game_id = f"game_{user_id}_{int(time.time())}"
        
        self.active_games[game_id] = {
            "user_id": user_id,
            "quiz_type": quiz_type,
            "questions": quiz_questions.copy(),
            "current_question": 0,
            "score": 0,
            "start_time": datetime.now().isoformat(),
            "answers": []
        }
        
        return {
            "success": True,
            "game_id": game_id,
            "question_count": len(quiz_questions),
            "first_question": self._format_question(quiz_questions[0], 0)
        }
    
    def _format_question(self, question: Dict, index: int) -> str:
        """Format question for display"""
        formatted = f"❓ שאלה {index + 1}: {question['question']}\n\n"
        
        options = question['options']
        letters = ['א', 'ב', 'ג', 'ד']
        
        for i, (letter, option) in enumerate(zip(letters, options)):
            formatted += f"{letter}. {option}\n"
        
        formatted += f"\n🎯 נקודות: {question['points']}"
        return formatted
    
    def answer_question(self, game_id: str, answer_index: int) -> Dict:
        """Process answer to current question"""
        if game_id not in self.active_games:
            return {"success": False, "error": "Game not found"}
        
        game = self.active_games[game_id]
        current_q = game["current_question"]
        
        if current_q >= len(game["questions"]):
            return {"success": False, "error": "Quiz completed"}
        
        question = game["questions"][current_q]
        is_correct = (answer_index == question["correct"])
        
        # Update game state
        if is_correct:
            game["score"] += question["points"]
        
        game["answers"].append({
            "question_index": current_q,
            "answer": answer_index,
            "correct": question["correct"],
            "is_correct": is_correct,
            "points": question["points"] if is_correct else 0
        })
        
        game["current_question"] += 1
        
        result = {
            "success": True,
            "correct": is_correct,
            "points_earned": question["points"] if is_correct else 0,
            "total_score": game["score"],
            "correct_answer": question["correct"],
            "explanation": self._get_explanation(question, answer_index),
            "completed": (game["current_question"] >= len(game["questions"]))
        }
        
        # If quiz completed, save score
        if result["completed"]:
            self._save_score(game_id, game)
            del self.active_games[game_id]
        
        return result
    
    def _get_explanation(self, question: Dict, user_answer: int) -> str:
        """Get explanation for answer"""
        correct_index = question["correct"]
        
        if user_answer == correct_index:
            return "🎉 תשובה נכונה! מצוין!"
        else:
            correct_option = question['options'][correct_index]
            letters = ['א', 'ב', 'ג', 'ד']
            return f"❌ לא נכון. התשובה הנכונה היא {letters[correct_index]}. {correct_option}"
    
    def _save_score(self, game_id: str, game: Dict):
        """Save quiz score to database"""
        user_id = game["user_id"]
        
        if str(user_id) not in quiz_scores_db:
            quiz_scores_db[str(user_id)] = []
        
        quiz_scores_db[str(user_id)].append({
            "game_id": game_id,
            "quiz_type": game["quiz_type"],
            "score": game["score"],
            "total_possible": sum(q["points"] for q in game["questions"]),
            "date": datetime.now().isoformat(),
            "answers": game["answers"]
        })
        
        save_json(QUIZ_FILE, quiz_scores_db)
        
        # Record in DNA learning
        advanced_dna._analyze_user_pattern(
            user_id, 
            "quiz_completed", 
            {"score": game["score"], "type": game["quiz_type"]}
        )
    
    def get_leaderboard(self, quiz_type: str = None) -> List[Dict]:
        """Get quiz leaderboard"""
        leaderboard = []
        
        for user_id_str, scores in quiz_scores_db.items():
            if not scores:
                continue
                
            user_scores = scores
            if quiz_type:
                user_scores = [s for s in scores if s.get("quiz_type") == quiz_type]
            
            if user_scores:
                total_score = sum(s.get("score", 0) for s in user_scores)
                best_score = max(s.get("score", 0) for s in user_scores)
                games_played = len(user_scores)
                
                # Get user info
                user_info = next((u for u in users_db if str(u.get("user_id")) == user_id_str), {})
                
                leaderboard.append({
                    "user_id": int(user_id_str),
                    "username": user_info.get("username", "Unknown"),
                    "first_name": user_info.get("first_name", "User"),
                    "total_score": total_score,
                    "best_score": best_score,
                    "games_played": games_played,
                    "avg_score": total_score / games_played
                })
        
        # Sort by total score
        leaderboard.sort(key=lambda x: x["total_score"], reverse=True)
        return leaderboard[:10]
    
    def create_custom_quiz(self, user_id: int, questions: List[Dict]) -> str:
        """Create custom quiz"""
        quiz_id = f"custom_{user_id}_{int(time.time())}"
        
        # Validate questions
        valid_questions = []
        for i, q in enumerate(questions):
            if all(k in q for k in ["question", "options", "correct"]):
                valid_questions.append({
                    "question": q["question"],
                    "options": q["options"][:4],  # Max 4 options
                    "correct": min(q["correct"], 3),  # 0-3
                    "points": q.get("points", 10)
                })
        
        if valid_questions:
            self.quizzes[quiz_id] = valid_questions
            return quiz_id
        
        return None

# Initialize quiz system
quiz_system = QuizGameSystem()

# ==================== TASK MANAGEMENT SYSTEM ====================
class TaskManager:
    """Task and reminder management system"""
    
    def __init__(self):
        self.scheduled_tasks = []
        self.module_id = advanced_dna.register_advanced_module(
            module_name="task_manager",
            module_type="productivity",
            functions=[
                "create_task",
                "list_tasks",
                "complete_task",
                "set_reminder",
                "get_statistics"
            ],
            dependencies=["core_bot"],
            complexity=2
        )
        
        # Start background task checker
        self._start_task_checker()
    
    def _start_task_checker(self):
        """Start background task checking thread"""
        def check_tasks():
            while True:
                try:
                    self._check_due_tasks()
                    time.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Task checker error: {e}")
                    time.sleep(300)
        
        thread = threading.Thread(target=check_tasks, daemon=True)
        thread.start()
    
    def _check_due_tasks(self):
        """Check for due tasks and send reminders"""
        now = datetime.now()
        
        for task in tasks_db:
            if not task.get('completed') and task.get('reminder_time'):
                reminder_time = datetime.fromisoformat(task['reminder_time'])
                
                if now >= reminder_time:
                    # Send reminder
                    self._send_task_reminder(task)
                    
                    # Update task to avoid duplicate reminders
                    task['last_reminded'] = now.isoformat()
                    if task.get('repeat') != "daily":
                        task['reminder_sent'] = True
                    
                    save_json(TASKS_FILE, tasks_db)
    
    def _send_task_reminder(self, task: Dict):
        """Send task reminder to user"""
        try:
            user_id = task['user_id']
            task_text = task['description']
            
            reminder_msg = (
                f"🔔 *תזכורת למשימה!*\n\n"
                f"📝 *משימה:* {task_text}\n"
                f"⏰ *נקבעה ל:* {task.get('due_date', 'לא מוגדר')}\n"
                f"🏷️ *קטגוריה:* {task.get('category', 'כללי')}\n\n"
                f"✅ לסמן כהשלמה: /task_complete_{task['id']}\n"
                f"📋 כל המשימות: /mytasks"
            )
            
            bot.send_message(
                chat_id=user_id,
                text=reminder_msg,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"Sent task reminder to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send task reminder: {e}")
    
    def create_task(self, user_id: int, description: str, 
                   due_date: str = None, category: str = "כללי",
                   priority: str = "medium", reminder_minutes: int = 60) -> Dict:
        """Create new task"""
        task_id = len(tasks_db) + 1
        
        # Parse due date
        reminder_time = None
        if due_date:
            try:
                due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                reminder_dt = due_dt - timedelta(minutes=reminder_minutes)
                reminder_time = reminder_dt.isoformat()
            except:
                # If can't parse, set reminder for 1 hour from now
                reminder_time = (datetime.now() + timedelta(minutes=60)).isoformat()
        
        task = {
            'id': task_id,
            'user_id': user_id,
            'description': description,
            'category': category,
            'priority': priority,
            'created': datetime.now().isoformat(),
            'due_date': due_date,
            'reminder_time': reminder_time,
            'completed': False,
            'completed_date': None,
            'reminder_sent': False,
            'repeat': None
        }
        
        tasks_db.append(task)
        save_json(TASKS_FILE, tasks_db)
        
        # Update DNA learning
        advanced_dna._analyze_user_pattern(
            user_id, 
            "task_created", 
            {"category": category, "priority": priority}
        )
        
        response = {
            "success": True,
            "task_id": task_id,
            "message": f"✅ משימה נוצרה בהצלחה! (מזהה: {task_id})"
        }
        
        if reminder_time:
            reminder_dt = datetime.fromisoformat(reminder_time)
            response["reminder"] = reminder_dt.strftime("%d/%m/%Y %H:%M")
        
        return response
    
    def list_tasks(self, user_id: int, category: str = None, 
                  show_completed: bool = False) -> List[Dict]:
        """List user's tasks"""
        user_tasks = [t for t in tasks_db if t['user_id'] == user_id]
        
        if category:
            user_tasks = [t for t in user_tasks if t.get('category') == category]
        
        if not show_completed:
            user_tasks = [t for t in user_tasks if not t.get('completed')]
        
        # Sort by priority and due date
        priority_order = {"high": 0, "medium": 1, "low": 2}
        user_tasks.sort(key=lambda x: (
            priority_order.get(x.get('priority', 'medium'), 1),
            x.get('due_date') or '9999-12-31'
        ))
        
        return user_tasks
    
    def complete_task(self, user_id: int, task_id: int) -> Dict:
        """Mark task as completed"""
        task = next((t for t in tasks_db 
                    if t['id'] == task_id and t['user_id'] == user_id), None)
        
        if not task:
            return {"success": False, "error": "Task not found"}
        
        task['completed'] = True
        task['completed_date'] = datetime.now().isoformat()
        save_json(TASKS_FILE, tasks_db)
        
        # Calculate completion time if there was a due date
        completion_stats = {}
        if task.get('due_date'):
            try:
                due_dt = datetime.fromisoformat(task['due_date'].replace('Z', '+00:00'))
                complete_dt = datetime.now()
                
                if complete_dt <= due_dt:
                    completion_stats['status'] = 'on_time'
                    completion_stats['days_early'] = (due_dt - complete_dt).days
                else:
                    completion_stats['status'] = 'late'
                    completion_stats['days_late'] = (complete_dt - due_dt).days
            except:
                pass
        
        return {
            "success": True,
            "task_id": task_id,
            "completion_stats": completion_stats,
            "message": f"✅ משימה {task_id} סומנה כהשלמה!"
        }
    
    def get_statistics(self, user_id: int) -> Dict:
        """Get task statistics for user"""
        user_tasks = [t for t in tasks_db if t['user_id'] == user_id]
        
        if not user_tasks:
            return {"total": 0, "completed": 0, "pending": 0}
        
        total = len(user_tasks)
        completed = len([t for t in user_tasks if t.get('completed')])
        pending = total - completed
        
        # By category
        by_category = {}
        for task in user_tasks:
            cat = task.get('category', 'כללי')
            by_category[cat] = by_category.get(cat, 0) + 1
        
        # By priority
        by_priority = {"high": 0, "medium": 0, "low": 0}
        for task in user_tasks:
            priority = task.get('priority', 'medium')
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        # Completion rate
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "completion_rate": round(completion_rate, 1),
            "by_category": by_category,
            "by_priority": by_priority
        }

# Initialize task manager
task_manager = TaskManager()

# ==================== ENHANCED HELPER FUNCTIONS ====================
def is_admin(user_id):
    """Check if user is admin"""
    return ADMIN_USER_ID and str(user_id) == ADMIN_USER_ID

def should_respond(update):
    """Enhanced response checking with learning patterns"""
    message = update.message
    if not message:
        return False
    
    user_id = update.effective_user.id
    
    # Check user preference from DNA learning
    user_patterns = advanced_dna.learning_data.get("user_patterns", {}).get(str(user_id), {})
    interaction_style = user_patterns.get("interaction_style", "responsive")
    
    # Always respond to commands
    if message.entities and any(entity.type == 'bot_command' for entity in message.entities):
        return True
    
    # Check if in private chat - always respond
    if message.chat.type == 'private':
        # But check user preference
        if interaction_style == "minimal" and "בוט" not in message.text:
            return False
        return True
    
    # Check if bot is mentioned in group
    if BOT_USERNAME and message.text and f"@{BOT_USERNAME}" in message.text:
        return True
    
    # Check if message is a reply to bot's message
    if message.reply_to_message and message.reply_to_message.from_user.id == BOT_ID:
        return True
    
    # For groups, check learning patterns
    triggers = [f"@{BOT_USERNAME}", "בוט", "רובוט", "עזרה", "help", "אסיסטנט"]
    
    # Add personalized triggers from learning
    if user_patterns.get("preferred_features"):
        for feature in user_patterns["preferred_features"][:3]:
            if feature.lower() in message.text.lower():
                return True
    
    if message.text and any(trigger in message.text.lower() for trigger in triggers):
        return True
    
    return False

def get_or_create_user(user_data, chat_type='private'):
    """Enhanced user creation with learning data"""
    user_id = user_data['id']
    
    for user in users_db:
        if user['user_id'] == user_id:
            # Update user info with enhanced data
            updates = {
                'username': user_data.get('username'),
                'first_name': user_data.get('first_name'),
                'last_name': user_data.get('last_name'),
                'last_seen': datetime.now().isoformat(),
                'chat_type': chat_type,
                'message_count': user.get('message_count', 0) + 1,
                'preferences': user.get('preferences', {}),
                'stats': {
                    'total_interactions': user.get('stats', {}).get('total_interactions', 0) + 1,
                    'last_command': None,
                    'favorite_features': user.get('stats', {}).get('favorite_features', [])
                }
            }
            user.update(updates)
            save_json(USERS_FILE, users_db)
            
            # Update active users in stats
            bot_stats.update('user_active', {'user_id': user_id})
            
            return user
    
    # Create new user with enhanced profile
    new_user = {
        'user_id': user_id,
        'username': user_data.get('username'),
        'first_name': user_data.get('first_name'),
        'last_name': user_data.get('last_name'),
        'first_seen': datetime.now().isoformat(),
        'last_seen': datetime.now().isoformat(),
        'chat_type': chat_type,
        'message_count': 1,
        'is_admin': is_admin(user_id),
        'preferences': {
            'language': 'hebrew',
            'notifications': True,
            'theme': 'default'
        },
        'stats': {
            'total_interactions': 1,
            'commands_used': {},
            'favorite_features': [],
            'engagement_score': 0.5
        },
        'achievements': [],
        'level': 1,
        'experience': 0
    }
    users_db.append(new_user)
    save_json(USERS_FILE, users_db)
    
    # Update DNA learning
    advanced_dna.learning_data["user_patterns"][str(user_id)] = {
        "first_seen": datetime.now().isoformat(),
        "command_frequency": {},
        "activity_times": [datetime.now().hour],
        "preferred_features": [],
        "interaction_style": "neutral",
        "trust_level": 0.5
    }
    advanced_dna._save_learning_data()
    
    bot_stats.update('user_active', {'user_id': user_id})
    
    return new_user

def register_group(chat):
    """Enhanced group registration"""
    chat_id = chat.id
    
    for group in groups_db:
        if group['chat_id'] == chat_id:
            group['last_activity'] = datetime.now().isoformat()
            group['title'] = chat.title
            group['member_count'] = chat.get_members_count() if hasattr(chat, 'get_members_count') else group.get('member_count', 0)
            group['active'] = True
            
            # Update group stats
            if 'stats' not in group:
                group['stats'] = {}
            group['stats']['interaction_count'] = group['stats'].get('interaction_count', 0) + 1
            group['stats']['last_bot_interaction'] = datetime.now().isoformat()
            
            save_json(GROUPS_FILE, groups_db)
            return group
    
    # Create new group record with enhanced data
    new_group = {
        'chat_id': chat_id,
        'title': chat.title,
        'type': chat.type,
        'first_seen': datetime.now().isoformat(),
        'last_activity': datetime.now().isoformat(),
        'member_count': chat.get_members_count() if hasattr(chat, 'get_members_count') else 0,
        'active': True,
        'settings': {
            'welcome_message': True,
            'goodbye_message': False,
            'anti_spam': True,
            'max_warnings': 3
        },
        'stats': {
            'interaction_count': 1,
            'unique_users': 1,
            'message_count': 0,
            'last_bot_interaction': datetime.now().isoformat()
        },
        'admins': [],
        'rules': None
    }
    groups_db.append(new_group)
    bot_stats.stats['groups'].add(chat_id)
    save_json(GROUPS_FILE, groups_db)
    return new_group

def log_message(update, command=None):
    """Enhanced message logging with analytics"""
    message = update.message
    if not message:
        return
    
    user = update.effective_user
    chat = update.effective_chat
    
    # Update or create user
    user_data = {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name
    }
    user_record = get_or_create_user(user_data, chat.type)
    
    # Update user stats
    if command:
        user_record['stats']['commands_used'][command] = \
            user_record['stats']['commands_used'].get(command, 0) + 1
        user_record['stats']['last_command'] = command
        
        # Update engagement score
        interaction_count = user_record['stats']['total_interactions']
        user_record['stats']['engagement_score'] = \
            min(1.0, 0.5 + (interaction_count * 0.01))
    
    # Register group if in group
    if chat.type in ['group', 'supergroup']:
        group_record = register_group(chat)
        
        # Update group stats
        if 'stats' in group_record:
            group_record['stats']['message_count'] = \
                group_record['stats'].get('message_count', 0) + 1
            
            # Track unique users in group
            if 'unique_users' not in group_record['stats']:
                group_record['stats']['unique_users'] = set()
            group_record['stats']['unique_users'].add(user.id)
    
    # Create enhanced message log
    message_log = {
        'message_id': message.message_id,
        'user_id': user.id,
        'chat_id': chat.id,
        'chat_type': chat.type,
        'text': message.text,
        'command': command,
        'timestamp': datetime.now().isoformat(),
        'bot_mentioned': BOT_USERNAME and message.text and f"@{BOT_USERNAME}" in message.text,
        'has_media': bool(message.photo or message.video or message.document),
        'reply_to': message.reply_to_message.message_id if message.reply_to_message else None,
        'language': 'hebrew' if any(c in '\u0590-\u05FF' for c in message.text or '') else 'other'
    }
    
    messages_db.append(message_log)
    if len(messages_db) > 5000:  # Keep last 5000 messages
        messages_db.pop(0)
    save_json(MESSAGES_FILE, messages_db)
    
    # Update statistics
    bot_stats.update('message')
    if command:
        bot_stats.update('command', {'command': command})
        bot_stats.update('feature_used', {'feature': command})
    
    # Update DNA learning
    if command:
        advanced_dna._analyze_user_pattern(user.id, command, {
            'chat_type': chat.type,
            'has_mention': message_log['bot_mentioned'],
            'timestamp': message_log['timestamp']
        })
    
    logger.info(f"📝 {chat.type.capitalize()} message from {user.first_name}: "
               f"{message.text[:50] if message.text else 'No text'}")

def escape_markdown_v2(text):
    """Enhanced markdown escaping"""
    if not text:
        return ""
    
    # Escape special characters for Telegram MarkdownV2
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    # First escape backslashes
    text = text.replace('\\', '\\\\')
    
    # Then escape other special characters
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

# ==================== ENHANCED KEYBOARDS ====================
def get_main_keyboard(user_id=None):
    """Enhanced main menu keyboard with learning"""
    user_preferences = {}
    
    if user_id:
        user = next((u for u in users_db if u['user_id'] == user_id), None)
        if user:
            user_preferences = user.get('preferences', {})
    
    # Dynamic keyboard based on user preferences and usage
    base_buttons = [
        [KeyboardButton("📊 סטטיסטיקות"), KeyboardButton("ℹ️ מידע על הבוט")],
        [KeyboardButton("🧩 תכונות חדשות"), KeyboardButton("🎮 משחק")]
    ]
    
    # Add financial buttons if user shows interest
    if user_id:
        user_patterns = advanced_dna.learning_data.get("user_patterns", {}).get(str(user_id), {})
        if "stock" in str(user_patterns.get("command_frequency", {})):
            base_buttons[1].insert(0, KeyboardButton("📈 מניות"))
    
    # Add admin buttons if admin
    if user_id and is_admin(user_id):
        base_buttons.append([KeyboardButton("👑 ניהול"), KeyboardButton("⚙️ הגדרות מתקדמות")])
    else:
        base_buttons.append([KeyboardButton("👤 הפרופיל שלי"), KeyboardButton("📝 משימות")])
    
    base_buttons.append([KeyboardButton("❓ עזרה"), KeyboardButton("🔄 רענן")])
    
    return ReplyKeyboardMarkup(base_buttons, resize_keyboard=True, one_time_keyboard=False)

def get_admin_keyboard():
    """Enhanced admin menu keyboard"""
    keyboard = [
        [KeyboardButton("📢 שידור לכולם"), KeyboardButton("📈 סטטיסטיקות מתקדמות")],
        [KeyboardButton("👥 ניהול משתמשים"), KeyboardButton("🏢 ניהול קבוצות")],
        [KeyboardButton("🔧 תחזוקת מערכת"), KeyboardButton("📊 דוחות DNA")],
        [KeyboardButton("🧪 בדיקות מערכת"), KeyboardButton("⚙️ הגדרות")],
        [KeyboardButton("🏠 לתפריט הראשי"), KeyboardButton("🔄 אתחול בוט")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_financial_keyboard():
    """Financial features keyboard"""
    keyboard = [
        [KeyboardButton("💹 מחיר מניה"), KeyboardButton("📊 ניתוח מניה")],
        [KeyboardButton("💱 שערי חליפין"), KeyboardButton("📅 אירועים כלכליים")],
        [KeyboardButton("📈 מדדים"), KeyboardButton("💰 תיק השקעות")],
        [KeyboardButton("🏠 לתפריט הראשי"), KeyboardButton("❓ עזרה פיננסית")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_game_keyboard():
    """Game features keyboard"""
    keyboard = [
        [KeyboardButton("🎯 התחל quiz"), KeyboardButton("🏆 טבלת שיאים")],
        [KeyboardButton("❓ שאלת טריוויה"), KeyboardButton("🎲 מזל")],
        [KeyboardButton("🧩 יצירת quiz"), KeyboardButton("📊 סטטיסטיקות משחק")],
        [KeyboardButton("🏠 לתפריט הראשי"), KeyboardButton("🎮 תפריט משחקים")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_task_keyboard():
    """Task management keyboard"""
    keyboard = [
        [KeyboardButton("➕ משימה חדשה"), KeyboardButton("📋 כל המשימות")],
        [KeyboardButton("✅ השלמת משימה"), KeyboardButton("📊 סטטיסטיקות משימות")],
        [KeyboardButton("⏰ תזכורות"), KeyboardButton("🏷️ קטגוריות")],
        [KeyboardButton("🏠 לתפריט הראשי"), KeyboardButton("🔄 רענן משימות")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# ==================== ENHANCED DNA FUNCTIONS ====================
def register_existing_modules():
    """Enhanced module registration"""
    
    # Enhanced core module
    advanced_dna.register_advanced_module(
        module_name="core_bot_enhanced",
        module_type="core",
        functions=["start", "help", "menu", "admin", "stats", "profile", "settings"],
        dependencies=[],
        complexity=1
    )
    
    # Enhanced user management
    advanced_dna.register_advanced_module(
        module_name="user_management_pro",
        module_type="management",
        functions=["get_or_create_user", "register_group", "log_message", "analyze_behavior"],
        dependencies=["core_bot_enhanced"],
        complexity=2
    )
    
    # Webhook handler
    advanced_dna.register_advanced_module(
        module_name="webhook_handler_secure",
        module_type="integration",
        functions=["webhook", "auth_check", "rate_limit"],
        dependencies=["core_bot_enhanced"],
        complexity=2
    )
    
    # Financial module
    advanced_dna.register_advanced_module(
        module_name="financial_module",
        module_type="financial",
        functions=["stock_price", "analysis", "exchange", "calendar"],
        dependencies=["core_bot_enhanced"],
        complexity=3
    )
    
    # Game module
    advanced_dna.register_advanced_module(
        module_name="game_entertainment",
        module_type="entertainment",
        functions=["quiz", "leaderboard", "trivia", "games"],
        dependencies=["core_bot_enhanced"],
        complexity=2
    )
    
    # Task module
    advanced_dna.register_advanced_module(
        module_name="task_productivity",
        module_type="productivity",
        functions=["create_task", "reminders", "statistics", "categories"],
        dependencies=["core_bot_enhanced"],
        complexity=2
    )
    
    logger.info("🧬 Registered enhanced modules in DNA")

def auto_evolve_check():
    """Enhanced auto-evolution check"""
    try:
        # Get evolution report
        report = advanced_dna.get_evolution_report()
        
        # Check if evolution is needed
        fitness = report["dna_info"]["fitness_score"]
        last_evolution = report["dna_info"].get("last_evolution")
        
        # Calculate days since last evolution
        days_since_last = 0
        if last_evolution:
            try:
                last_dt = datetime.fromisoformat(last_evolution)
                days_since_last = (datetime.now() - last_dt).days
            except:
                days_since_last = 0
        
        # Trigger evolution based on conditions
        should_evolve = False
        reason = ""
        
        if days_since_last >= 7:
            should_evolve = True
            reason = f"זמן מאז אבולוציה אחרונה: {days_since_last} ימים"
        elif fitness < 70 and len(messages_db) > 100:
            should_evolve = True
            reason = f"דירוג התאמה נמוך: {fitness}, הודעות: {len(messages_db)}"
        elif bot_stats.stats['errors_count'] > 20:
            should_evolve = True
            reason = f"שגיאות רבות: {bot_stats.stats['errors_count']}"
        
        if should_evolve:
            logger.info(f"🧬 Triggering auto-evolution: {reason}")
            
            # Analyze and evolve
            result = advanced_dna.analyze_and_evolve()
            
            if result.get("success"):
                evolution_id = result.get("evolution_id")
                steps = result.get("steps_executed", 0)
                
                logger.info(f"🧬 Auto-evolution {evolution_id} completed with {steps} steps")
                
                # Notify admin
                if ADMIN_USER_ID:
                    try:
                        bot.send_message(
                            chat_id=ADMIN_USER_ID,
                            text=f"🤖 *אבולוציה אוטומטית התרחשה!*\n\n"
                                 f"*סיבה:* {reason}\n"
                                 f"*מזהה אבולוציה:* {evolution_id}\n"
                                 f"*שלבים שבוצעו:* {steps}\n"
                                 f"*דירוג התאמה חדש:* {advanced_dna.dna.get('fitness_score')}\n\n"
                                 f"_המערכת מתאימה את עצמה אוטומטית..._",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin: {e}")
    
    except Exception as e:
        logger.error(f"Error in auto_evolve_check: {e}")

# ==================== ENHANCED DNA COMMANDS ====================
def dna_command(update, context):
    """Enhanced DNA command with detailed report"""
    log_message(update, 'dna')
    
    report = advanced_dna.get_evolution_report()
    dna_info = report["dna_info"]
    
    dna_text = (
        f"🧬 *DNA מתקדם של {BOT_NAME}*\n\n"
        f"*פרטים גנטיים:*\n"
        f"• 🆔 דור: {dna_info['generation']}\n"
        f"• 🏷️ שם: {BOT_NAME}\n"
        f"• 📊 דירוג התאמה: {dna_info['fitness_score']}/100\n"
        f"• 🔄 רמת התאמה: {dna_info['adaptation_level']:.2f}\n"
        f"• 🧪 מוטציות: {dna_info['total_mutations']}\n"
        f"• 🧩 מודולים: {dna_info['total_modules']}\n\n"
    )
    
    # Evolution progress
    progress = report["progress"]
    dna_text += f"*התקדמות אבולוציה:*\n"
    dna_text += f"• 📈 רמה: {progress['level']}\n"
    dna_text += f"• 🎯 התקדמות: {progress['percent']:.1f}%\n"
    
    if progress['points_needed'] > 0:
        dna_text += f"• 🔜 אבן דרך הבאה: {progress['target']}% "
        dna_text += f"(נדרשים {progress['points_needed']:.1f} נקודות)\n\n"
    
    # Traits
    traits = report["traits"]
    dna_text += f"*תכונות:*\n"
    dna_text += f"• ⚡ תגובתיות: {traits.get('responsiveness', 0)*100:.0f}%\n"
    dna_text += f"• ✅ אמינות: {traits.get('reliability', 0)*100:.0f}%\n"
    dna_text += f"• 💡 חדשנות: {traits.get('innovation', 0)*100:.0f}%\n"
    dna_text += f"• 🏃 יעילות: {traits.get('efficiency', 0)*100:.0f}%\n\n"
    
    # Recent mutations
    recent_muts = report.get("recent_mutations", [])
    if recent_muts:
        dna_text += f"*מוטציות אחרונות:*\n"
        for mut in recent_muts[-3:]:
            mut_time = datetime.fromisoformat(mut['timestamp']).strftime('%d/%m')
            dna_text += f"• {mut['type']} ({mut_time}) - {mut.get('impact', 'medium')}\n"
    
    # Learning insights
    insights = report.get("learning_insights", {})
    dna_text += f"\n*תובנות למידה:*\n"
    dna_text += f"• 👤 דפוסי משתמשים: {insights.get('user_patterns_count', 0)}\n"
    dna_text += f"• 📝 דפוסי פקודות: {insights.get('command_patterns_count', 0)}\n"
    
    # Capabilities
    caps = report.get("capabilities", {})
    enabled_caps = [k for k, v in caps.items() if v]
    if enabled_caps:
        dna_text += f"\n*יכולות מופעלות:* {', '.join(enabled_caps)}\n"
    
    dna_text += f"\n_זמן מעודכן: {datetime.now().strftime('%H:%M')}_"
    
    update.message.reply_text(dna_text, parse_mode=ParseMode.MARKDOWN)

def evolve_command(update, context):
    """Enhanced evolve command"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    log_message(update, 'evolve')
    
    if not context.args:
        help_text = (
            "🔄 *אבולוציה מתקדמת*\n\n"
            "*שימושים:*\n"
            "`/evolve analyze` - ניתוח מערכת\n"
            "`/evolve execute` - הפעלת אבולוציה\n"
            "`/evolve status` - סטטוס מפורט\n"
            "`/evolve report` - דוח אבולוציה\n"
            "`/evolve learn` - ניתוח למידה\n\n"
            "*דוגמה:* `/evolve analyze`"
        )
        update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        return
    
    action = context.args[0].lower()
    
    if action == "analyze":
        # Analyze system for evolution
        patterns = advanced_dna._collect_patterns()
        analysis = advanced_dna._analyze_patterns(patterns)
        
        analysis_text = (
            f"🔍 *ניתוח מערכת לאבולוציה*\n\n"
            f"*מצב:* {'נדרשת אבולוציה ✅' if analysis['should_evolve'] else 'לא נדרשת אבולוציה ⏸️'}\n"
            f"*סוג אבולוציה מוצע:* {analysis['evolution_type'] or 'ללא'}\n"
            f"*רמת ביטחון:* {analysis['confidence']*100:.1f}%\n\n"
        )
        
        if analysis['reasons']:
            analysis_text += "*סיבות:*\n"
            for reason in analysis['reasons']:
                analysis_text += f"• {reason}\n"
        
        # Add system stats
        stats = bot_stats.get_summary()
        analysis_text += f"\n*סטטיסטיקות מערכת:*\n"
        analysis_text += f"• הודעות: {stats['total_messages']}\n"
        analysis_text += f"• משתמשים פעילים: {stats['active_users']}\n"
        analysis_text += f"• פקודות: {stats['commands_count']}\n"
        analysis_text += f"• שגיאות: {stats['errors_count']}\n"
        
        update.message.reply_text(analysis_text, parse_mode=ParseMode.MARKDOWN)
    
    elif action == "execute":
        # Execute evolution
        update.message.reply_text("🔄 *מתחיל תהליך אבולוציה...*", 
                                 parse_mode=ParseMode.MARKDOWN)
        
        result = advanced_dna.analyze_and_evolve()
        
        if result.get("success"):
            evolution_id = result.get("evolution_id")
            steps = result.get("steps_executed", 0)
            
            success_text = (
                f"✅ *אבולוציה הושלמה!*\n\n"
                f"*מזהה אבולוציה:* {evolution_id}\n"
                f"*שלבים שבוצעו:* {steps}\n"
                f"*מודולים חדשים:* {len(result.get('new_modules', []))}\n\n"
            )
            
            if result.get('new_modules'):
                success_text += "*מודולים שנוצרו:*\n"
                for module in result['new_modules'][:3]:
                    success_text += f"• {module.get('module_id', 'Unknown')}\n"
            
            success_text += f"\n_דירוג התאמה חדש: {advanced_dna.dna.get('fitness_score')}_"
            
            update.message.reply_text(success_text, parse_mode=ParseMode.MARKDOWN)
        else:
            update.message.reply_text(
                f"❌ *אבולוציה נכשלה:* {result.get('reason', 'Unknown error')}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif action == "status":
        # Detailed status
        report = advanced_dna.get_evolution_report()
        progress = report["progress"]
        
        status_text = (
            f"📊 *סטטוס אבולוציה מתקדם*\n\n"
            f"*דור נוכחי:* {report['dna_info']['generation']}\n"
            f"*רמת התפתחות:* {progress['level']}\n"
            f"*התקדמות:* {progress['percent']:.1f}%\n\n"
        )
        
        if progress['points_needed'] > 0:
            status_text += f"*לאבן דרך הבאה:*\n"
            status_text += f"• 🎯 יעד: {progress['target']}%\n"
            status_text += f"• 📈 נקודות נדרשות: {progress['points_needed']:.1f}\n"
            status_text += f"• 🧪 מוטציות משוערות: {progress['estimated_mutations']}\n\n"
        
        # Module status
        active_modules = [m for m in report.get('active_modules', [])]
        if active_modules:
            status_text += f"*מודולים פעילים:* {len(active_modules)}\n"
            for module in active_modules[:5]:
                status_text += f"• {module.get('name')} ({module.get('type')})\n"
        
        # Recent activity
        recent_muts = report['dna_info'].get('last_evolution')
        if recent_muts:
            last_dt = datetime.fromisoformat(recent_muts)
            days_ago = (datetime.now() - last_dt).days
            status_text += f"\n*אבולוציה אחרונה:* לפני {days_ago} יום{'ים' if days_ago > 1 else ''}"
        
        update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)
    
    elif action == "report":
        # Generate detailed report
        report = advanced_dna.get_evolution_report()
        
        # Create comprehensive report
        report_text = (
            f"📄 *דוח אבולוציה מלא*\n"
            f"*תאריך:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            f"*בוט:* {BOT_NAME}\n"
            f"*דור:* {report['dna_info']['generation']}\n"
            f"*דירוג התאמה:* {report['dna_info']['fitness_score']}/100\n\n"
        )
        
        # System metrics
        stats = bot_stats.get_summary()
        report_text += f"*מדדי מערכת:*\n"
        report_text += f"• זמן פעילות: {stats['uptime']}\n"
        report_text += f"• הודעות: {stats['total_messages']}\n"
        report_text += f"• משתמשים: {stats['total_users']}\n"
        report_text += f"• משתמשים פעילים: {stats['active_users']}\n"
        report_text += f"• פקודות: {stats['commands_count']}\n"
        report_text += f"• שגיאות: {stats['errors_count']}\n\n"
        
        # Top commands
        if stats['top_commands']:
            report_text += f"*פקודות פופולריות:*\n"
            for cmd, count in stats['top_commands']:
                report_text += f"• {cmd}: {count}\n"
        
        update.message.reply_text(report_text, parse_mode=ParseMode.MARKDOWN)
    
    elif action == "learn":
        # Learning analysis
        insights = advanced_dna.learning_data
        
        learn_text = (
            f"🧠 *ניתוח למידה ואינטליגנציה*\n\n"
            f"*דפוסי משתמשים:* {len(insights.get('user_patterns', {}))}\n"
            f"*דפוסי פקודות:* {len(insights.get('command_patterns', {}))}\n"
            f"*סך דפוסים:* {sum(len(v) for v in insights.values() if isinstance(v, dict))}\n\n"
        )
        
        # Show some user patterns
        user_patterns = insights.get('user_patterns', {})
        if user_patterns:
            sample_users = list(user_patterns.items())[:3]
            learn_text += f"*דוגמאות דפוסי משתמשים:*\n"
            
            for user_id, patterns in sample_users:
                user_info = next((u for u in users_db if str(u.get('user_id')) == user_id), {})
                user_name = user_info.get('first_name', 'Unknown')
                
                if patterns.get('command_frequency'):
                    top_cmd = max(patterns['command_frequency'].items(), 
                                key=lambda x: x[1], default=('none', 0))
                    learn_text += f"• {user_name}: {top_cmd[0]} ({top_cmd[1]} פעמים)\n"
        
        # System learning stats
        hourly_activity = bot_stats.get_hourly_activity()
        peak_hours = sorted(hourly_activity, key=lambda x: x['count'], reverse=True)[:3]
        
        if peak_hours:
            learn_text += f"\n*שעות פעילות שיא:*\n"
            for hour_data in peak_hours:
                learn_text += f"• {hour_data['hour']}:00 - {hour_data['count']} הודעות\n"
        
        learn_text += f"\n_למידה מתמשכת: {datetime.now().strftime('%H:%M')}_"
        
        update.message.reply_text(learn_text, parse_mode=ParseMode.MARKDOWN)

def lineage_command(update, context):
    """Enhanced lineage command"""
    log_message(update, 'lineage')
    
    if not context.args:
        # Show module list
        modules = advanced_dna.dna.get("modules", {})
        
        if not modules:
            update.message.reply_text("ℹ️ *אין מודולים רשומים ב-DNA*", 
                                     parse_mode=ParseMode.MARKDOWN)
            return
        
        modules_text = "📦 *מודולים זמינים לשושלת:*\n\n"
        
        for module_id, module in list(modules.items())[:10]:
            modules_text += f"• `{module_id}` - {module.get('name', 'ללא שם')} "
            modules_text += f"({module.get('type', 'ללא סוג')})\n"
        
        if len(modules) > 10:
            modules_text += f"\n+ {len(modules) - 10} מודולים נוספים..."
        
        modules_text += "\n*שימוש:* `/lineage module_id`"
        
        update.message.reply_text(modules_text, parse_mode=ParseMode.MARKDOWN)
        return
    
    module_id = context.args[0]
    module = advanced_dna.dna["modules"].get(module_id)
    
    if not module:
        # Try to find by name
        for mod_id, mod in advanced_dna.dna["modules"].items():
            if mod.get("name") == module_id:
                module = mod
                module_id = mod_id
                break
        
        if not module:
            update.message.reply_text(
                f"❌ *מודול לא נמצא:* `{module_id}`\n\n"
                f"השתמש ב`/lineage` ללא פרמטרים לראות רשימה.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
    
    # Get enhanced lineage info
    lineage_text = f"🌳 *שושלת מתקדמת: {module['name']}*\n\n"
    lineage_text += f"*פרטי מודול:*\n"
    lineage_text += f"• 🆔 מזהה: `{module_id}`\n"
    lineage_text += f"• 🏷️ סוג: {module.get('type')}\n"
    lineage_text += f"• 🧩 מורכבות: {module.get('complexity', 1)}/5\n"
    lineage_text += f"• 📅 נוצר: {datetime.fromisoformat(module['birth_date']).strftime('%d/%m/%Y')}\n"
    lineage_text += f"• 🔄 סטטוס: {module.get('status', 'active')}\n"
    
    # Dependencies
    deps = module.get('dependencies', [])
    if deps:
        lineage_text += f"\n*תלויות:*\n"
        for dep in deps:
            dep_module = advanced_dna.dna["modules"].get(dep, {})
            dep_name = dep_module.get('name', dep)
            lineage_text += f"• 📌 {dep_name}\n"
    
    # Functions
    funcs = module.get('functions', [])
    if funcs:
        lineage_text += f"\n*פונקציות:*\n"
        for func in funcs[:5]:
            lineage_text += f"• ⚙️ {func}\n"
        if len(funcs) > 5:
            lineage_text += f"• + {len(funcs) - 5} נוספות...\n"
    
    # Performance
    perf = module.get('performance', {})
    if perf:
        lineage_text += f"\n*ביצועים:*\n"
        lineage_text += f"• 📞 קריאות: {perf.get('calls', 0)}\n"
        lineage_text += f"• ✅ שיעור הצלחה: {perf.get('success_rate', 1)*100:.1f}%\n"
        if perf.get('avg_response_time'):
            lineage_text += f"• ⏱️ זמן תגובה ממוצע: {perf['avg_response_time']:.2f}s\n"
    
    # Mutations for this module
    module_mutations = [m for m in advanced_dna.dna['mutations'] 
                       if m.get('module_id') == module_id]
    
    if module_mutations:
        lineage_text += f"\n*מוטציות במודול זה:* {len(module_mutations)}\n"
        for mut in module_mutations[-3:]:
            mut_time = datetime.fromisoformat(mut['timestamp']).strftime('%d/%m')
            lineage_text += f"• {mut.get('type', 'unknown')} "
            lineage_text += f"({mut_time}) - {mut.get('impact', 'medium')}\n"
    
    # Generation info
    generation = len(module.get('dependencies', [])) + 1
    lineage_text += f"\n_דור: {generation}, גרסה: {module.get('version', '1.0')}_"
    
    update.message.reply_text(lineage_text, parse_mode=ParseMode.MARKDOWN)

def initialize_evolution():
    """Enhanced evolution initialization"""
    # Register enhanced modules
    register_existing_modules()
    
    # Register evolution system itself
    advanced_dna.register_advanced_module(
        module_name="evolution_system_pro",
        module_type="meta",
        functions=["analyze_and_evolve", "record_mutation", "learn_patterns", "predict_evolution"],
        dependencies=["core_bot_enhanced"],
        complexity=4
    )
    
    # Record foundation mutation
    advanced_dna.record_intelligent_mutation(
        module_id="core_bot_enhanced",
        mutation_type="foundation_built",
        description="Advanced evolutionary bot foundation established",
        impact="critical",
        trigger="initialization",
        confidence=1.0
    )
    
    # Record evolution system creation
    advanced_dna.record_intelligent_mutation(
        module_id="evolution_system_pro",
        mutation_type="meta_system_created",
        description="Advanced evolution meta-system initialized",
        impact="high",
        trigger="initialization",
        confidence=0.9
    )
    
    logger.info("🧬 Enhanced evolutionary system initialized")

# ==================== NEW FEATURE COMMANDS ====================
def stock_command(update, context):
    """Get stock price information"""
    log_message(update, 'stock')
    
    if not context.args:
        help_text = (
            "📈 *קבלת מידע על מניות*\n\n"
            "*שימוש:* `/stock <סימבול מניה>`\n\n"
            "*דוגמאות:*\n"
            "`/stock AAPL` - אפל\n"
            "`/stock TSLA` - טסלה\n"
            "`/stock GOOGL` - גוגל\n\n"
            "*הערה:* הסימבול חייב להיות באנגלית"
        )
        update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        return
    
    symbol = context.args[0].upper()
    
    # Send processing message
    processing_msg = update.message.reply_text(
        f"🔍 *מחפש מידע על {symbol}...*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Get stock data
    stock_data = financial_assistant.get_stock_price(symbol)
    
    if stock_data.get("success"):
        # Format response
        price = stock_data.get("price", "N/A")
        change = stock_data.get("change", "0")
        change_percent = stock_data.get("change_percent", "0%")
        volume = stock_data.get("volume", "N/A")
        latest_day = stock_data.get("latest_trading_day", "N/A")
        
        # Determine change emoji
        change_emoji = "📈" if change.startswith('+') else "📉" if change.startswith('-') else "➡️"
        
        stock_text = (
            f"{change_emoji} *{symbol} - מחיר מניה*\n\n"
            f"*💵 מחיר:* ${price}\n"
            f"*📊 שינוי:* {change} ({change_percent})\n"
            f"*📈 נפח:* {volume}\n"
            f"*📅 יום מסחר אחרון:* {latest_day}\n\n"
        )
        
        # Get additional analysis if available
        analysis = financial_assistant.get_stock_analysis(symbol)
        if analysis.get("success"):
            stock_text += f"*🏢 חברה:* {analysis.get('name', 'N/A')}\n"
            stock_text += f"*📊 מגזר:* {analysis.get('sector', 'N/A')}\n"
            
            market_cap = analysis.get('market_cap')
            if market_cap and market_cap != 'None':
                # Format market cap
                try:
                    market_cap_num = float(market_cap)
                    if market_cap_num >= 1e9:
                        market_cap = f"${market_cap_num/1e9:.2f}B"
                    elif market_cap_num >= 1e6:
                        market_cap = f"${market_cap_num/1e6:.2f}M"
                    stock_text += f"*💰 שווי שוק:* {market_cap}\n"
                except:
                    pass
            
            pe_ratio = analysis.get('pe_ratio')
            if pe_ratio and pe_ratio != 'None':
                stock_text += f"*📐 יחס P/E:* {pe_ratio}\n"
        
        stock_text += f"\n_מידע עדכני נכון ל: {datetime.now().strftime('%H:%M')}_"
        
        # Update processing message
        processing_msg.edit_text(stock_text, parse_mode=ParseMode.MARKDOWN)
        
        # Update DNA learning
        advanced_dna._analyze_user_pattern(
            update.effective_user.id, 
            "stock_check", 
            {"symbol": symbol, "success": True}
        )
        
    else:
        error_msg = stock_data.get("error", "Unknown error")
        processing_msg.edit_text(
            f"❌ *שגיאה בקבלת מידע על {symbol}:*\n\n{error_msg}\n\n"
            f"נסה שנית או בדוק את הסימבול.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Update DNA learning with error
        bot_stats.update('error')

def analyze_command(update, context):
    """Get detailed stock analysis"""
    log_message(update, 'analyze')
    
    if not context.args:
        update.message.reply_text(
            "📊 *ניתוח מניות מתקדם*\n\n"
            "*שימוש:* `/analyze <סימבול מניה>`\n\n"
            "*דוגמה:* `/analyze AAPL`\n\n"
            "*הערה:* מציג מידע מפורט על החברה והמניה",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    symbol = context.args[0].upper()
    
    processing_msg = update.message.reply_text(
        f"🔍 *מנתח את {symbol}...*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Get analysis
    analysis = financial_assistant.get_stock_analysis(symbol)
    
    if analysis.get("success"):
        analysis_text = (
            f"📊 *ניתוח מניה: {analysis.get('name', symbol)} ({symbol})*\n\n"
        )
        
        # Basic info
        analysis_text += f"*🏢 חברה:* {analysis.get('name', 'N/A')}\n"
        analysis_text += f"*📝 תיאור:* {analysis.get('description', 'אין תיאור')[:200]}...\n\n"
        
        # Sector and industry
        sector = analysis.get('sector', 'N/A')
        industry = analysis.get('industry', 'N/A')
        analysis_text += f"*🏭 מגזר:* {sector}\n"
        analysis_text += f"*🏗️ תעשייה:* {industry}\n\n"
        
        # Financial metrics
        metrics_text = "*📈 מדדים פיננסיים:*\n"
        
        market_cap = analysis.get('market_cap')
        if market_cap and market_cap != 'None':
            try:
                market_cap_num = float(market_cap)
                if market_cap_num >= 1e12:
                    market_cap = f"${market_cap_num/1e12:.2f}T"
                elif market_cap_num >= 1e9:
                    market_cap = f"${market_cap_num/1e9:.2f}B"
                elif market_cap_num >= 1e6:
                    market_cap = f"${market_cap_num/1e6:.2f}M"
                metrics_text += f"• שווי שוק: {market_cap}\n"
            except:
                pass
        
        pe_ratio = analysis.get('pe_ratio')
        if pe_ratio and pe_ratio != 'None':
            pe_float = float(pe_ratio)
            pe_status = "נמוך" if pe_float < 15 else "בינוני" if pe_float < 25 else "גבוה"
            metrics_text += f"• יחס P/E: {pe_ratio} ({pe_status})\n"
        
        eps = analysis.get('eps')
        if eps and eps != 'None':
            metrics_text += f"• EPS: ${eps}\n"
        
        dividend = analysis.get('dividend_yield')
        if dividend and dividend != 'None':
            metrics_text += f"• דיבידנד: {float(dividend)*100:.2f}%\n"
        
        beta = analysis.get('beta')
        if beta and beta != 'None':
            beta_float = float(beta)
            volatility = "נמוכה" if beta_float < 0.8 else "בינונית" if beta_float < 1.2 else "גבוהה"
            metrics_text += f"• בטא: {beta} (תנודתיות {volatility})\n"
        
        analysis_text += metrics_text
        
        # Get current price for context
        price_data = financial_assistant.get_stock_price(symbol)
        if price_data.get("success"):
            current_price = price_data.get("price", "N/A")
            analysis_text += f"\n*💵 מחיר נוכחי:* ${current_price}"
        
        analysis_text += f"\n\n_מידע אנליטי, לא ייעוץ השקעות_"
        
        processing_msg.edit_text(analysis_text, parse_mode=ParseMode.MARKDOWN)
        
        # Update DNA learning
        advanced_dna._analyze_user_pattern(
            update.effective_user.id, 
            "stock_analysis", 
            {"symbol": symbol, "metrics_count": len([k for k in analysis.keys() if analysis[k]])}
        )
        
    else:
        processing_msg.edit_text(
            f"❌ *לא ניתן לנתח את {symbol}*\n\n"
            f"הסיבה: {analysis.get('error', 'Unknown error')}\n\n"
            f"נסה שנית מאוחר יותר.",
            parse_mode=ParseMode.MARKDOWN
        )

def exchange_command(update, context):
    """Get currency exchange rates"""
    log_message(update, 'exchange')
    
    if len(context.args) < 2:
        help_text = (
            "💱 *שערי חליפין*\n\n"
            "*שימוש:* `/exchange <מטבע from> <מטבע to>`\n\n"
            "*דוגמאות:*\n"
            "`/exchange USD ILS` - דולר לשקל\n"
            "`/exchange EUR USD` - אירו לדולר\n"
            "`/exchange GBP EUR` - לירה שטרלינג לאירו\n\n"
            "*קודים נפוצים:* USD, EUR, GBP, JPY, ILS, CAD, AUD"
        )
        update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        return
    
    from_curr = context.args[0].upper()
    to_curr = context.args[1].upper()
    
    processing_msg = update.message.reply_text(
        f"💱 *מחפש שער חליפין {from_curr} → {to_curr}...*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Get exchange rate
    rate_data = financial_assistant.get_exchange_rate(from_curr, to_curr)
    
    if rate_data.get("success"):
        rate = rate_data.get("rate", "N/A")
        bid = rate_data.get("bid", "N/A")
        ask = rate_data.get("ask", "N/A")
        timestamp = rate_data.get("timestamp", "N/A")
        
        # Format timestamp
        try:
            ts_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_ts = ts_dt.strftime("%d/%m/%Y %H:%M")
        except:
            formatted_ts = timestamp
        
        exchange_text = (
            f"💱 *שער חליפין:* {from_curr} → {to_curr}\n\n"
            f"*🔢 שער:* 1 {from_curr} = {rate} {to_curr}\n"
            f"*💰 Bid:* {bid}\n"
            f"*💵 Ask:* {ask}\n"
            f"*⏰ עודכן:* {formatted_ts}\n\n"
        )
        
        # Calculate inverse rate
        try:
            inverse_rate = 1 / float(rate)
            exchange_text += f"*🔄 שער הפוך:* 1 {to_curr} = {inverse_rate:.4f} {from_curr}\n\n"
        except:
            pass
        
        # Add common conversions
        common_amounts = [10, 50, 100, 500, 1000]
        exchange_text += "*💸 המרות נפוצות:*\n"
        
        try:
            rate_float = float(rate)
            for amount in common_amounts:
                converted = amount * rate_float
                exchange_text += f"• {amount} {from_curr} = {converted:.2f} {to_curr}\n"
        except:
            exchange_text += "• לא ניתן לחשב המרות\n"
        
        exchange_text += f"\n_שערים מסחריים, עשויים להשתנות_"
        
        processing_msg.edit_text(exchange_text, parse_mode=ParseMode.MARKDOWN)
        
        # Update DNA learning
        advanced_dna._analyze_user_pattern(
            update.effective_user.id, 
            "exchange_check", 
            {"from": from_curr, "to": to_curr, "rate": rate}
        )
        
    else:
        processing_msg.edit_text(
            f"❌ *שגיאה בקבלת שער חליפין*\n\n"
            f"{rate_data.get('error', 'Unknown error')}\n\n"
            f"ודא שהקודים תקינים (למשל: USD, EUR, ILS).",
            parse_mode=ParseMode.MARKDOWN
        )

def quiz_command(update, context):
    """Start a quiz game"""
    log_message(update, 'quiz')
    
    quiz_types = ["trivia", "tech", "finance"]
    
    if not context.args:
        # Show quiz type selection
        keyboard = []
        row = []
        for i, quiz_type in enumerate(quiz_types):
            hebrew_names = {
                "trivia": "טריוויה",
                "tech": "טכנולוגיה",
                "finance": "פיננסים"
            }
            row.append(InlineKeyboardButton(
                hebrew_names.get(quiz_type, quiz_type), 
                callback_data=f"quiz_start_{quiz_type}"
            ))
            
            if (i + 1) % 2 == 0 or i == len(quiz_types) - 1:
                keyboard.append(row)
                row = []
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "🎯 *בחר סוג quiz:*\n\n"
            "• 🧠 *טריוויה* - שאלות ידע כללי\n"
            "• 💻 *טכנולוגיה* - שאלות טק ותכנות\n"
            "• 💰 *פיננסים* - שאלות כלכלה ושוק ההון\n\n"
            "לחץ על הכפתור המתאים או השתמש ב:`/quiz <סוג>`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return
    
    quiz_type = context.args[0].lower()
    
    if quiz_type not in quiz_types:
        update.message.reply_text(
            f"❌ *סוג quiz לא תקף:* {quiz_type}\n\n"
            f"סוגים זמינים: {', '.join(quiz_types)}\n"
            f"דוגמה: `/quiz trivia`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Start quiz
    user_id = update.effective_user.id
    result = quiz_system.start_quiz(user_id, quiz_type)
    
    if result.get("success"):
        game_id = result["game_id"]
        question_count = result["question_count"]
        first_question = result["first_question"]
        
        # Create answer buttons
        keyboard = []
        letters = ['א', 'ב', 'ג', 'ד']
        for i, letter in enumerate(letters):
            keyboard.append([InlineKeyboardButton(
                f"{letter}", 
                callback_data=f"quiz_answer_{game_id}_{i}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        quiz_text = (
            f"🎮 *Quiz התחיל!*\n"
            f"*סוג:* {quiz_type}\n"
            f"*מספר שאלות:* {question_count}\n\n"
            f"{first_question}\n\n"
            f"*לחץ על הכפתור עם התשובה הנכונה:*"
        )
        
        update.message.reply_text(
            quiz_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text(
            f"❌ *לא ניתן להתחיל quiz:* {result.get('error', 'Unknown error')}",
            parse_mode=ParseMode.MARKDOWN
        )

def leaderboard_command(update, context):
    """Show quiz leaderboard"""
    log_message(update, 'leaderboard')
    
    quiz_type = context.args[0].lower() if context.args else None
    
    # Get leaderboard
    leaderboard = quiz_system.get_leaderboard(quiz_type)
    
    if not leaderboard:
        update.message.reply_text(
            "🏆 *טבלת שיאים*\n\n"
            "אין עדיין תוצאות ב-quiz.\n"
            "התחל quiz עם `/quiz` כדי להופיע כאן!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    leaderboard_text = "🏆 *טבלת שיאים - Quiz*\n\n"
    
    if quiz_type:
        hebrew_names = {
            "trivia": "טריוויה",
            "tech": "טכנולוגיה",
            "finance": "פיננסים"
        }
        leaderboard_text += f"*קטגוריה:* {hebrew_names.get(quiz_type, quiz_type)}\n\n"
    
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, player in enumerate(leaderboard[:10]):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        username = player.get('username', '')
        if username:
            username = f"(@{username})"
        
        leaderboard_text += (
            f"{medal} *{player['first_name']}* {username}\n"
            f"   📊 ניקוד: {player['total_score']} | 🎮 משחקים: {player['games_played']} | "
            f"⭐ ממוצע: {player['avg_score']:.1f}\n\n"
        )
    
    # Add user's own position if not in top 10
    user_id = update.effective_user.id
    user_position = None
    
    for i, player in enumerate(leaderboard):
        if player['user_id'] == user_id:
            user_position = i + 1
            break
    
    if user_position and user_position > 10:
        user_player = leaderboard[user_position - 1]
        leaderboard_text += (
            f"\n📊 *המיקום שלך:* #{user_position}\n"
            f"ניקוד: {user_player['total_score']} | משחקים: {user_player['games_played']}"
        )
    
    leaderboard_text += f"\n_עודכן: {datetime.now().strftime('%H:%M')}_"
    
    update.message.reply_text(leaderboard_text, parse_mode=ParseMode.MARKDOWN)

def task_command(update, context):
    """Task management command"""
    log_message(update, 'task')
    
    if not context.args:
        # Show task management options
        update.message.reply_text(
            "📝 *ניהול משימות*\n\n"
            "*פקודות זמינות:*\n"
            "`/task new <תיאור>` - משימה חדשה\n"
            "`/task list` - כל המשימות\n"
            "`/task stats` - סטטיסטיקות\n"
            "`/task complete <מספר>` - השלמת משימה\n\n"
            "*דוגמאות:*\n"
            "`/task new לקנות לחם`\n"
            "`/task new ישיבת עבודה --due 2024-12-20T14:00`\n"
            "`/task complete 5`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_task_keyboard()
        )
        return
    
    subcommand = context.args[0].lower()
    user_id = update.effective_user.id
    
    if subcommand == "new" and len(context.args) > 1:
        # Create new task
        description = ' '.join(context.args[1:])
        
        # Parse optional parameters
        due_date = None
        category = "כללי"
        priority = "medium"
        
        # Check for --due parameter
        if '--due' in description:
            parts = description.split('--due')
            description = parts[0].strip()
            if len(parts) > 1:
                due_part = parts[1].strip()
                # Try to parse date
                try:
                    # Support various date formats
                    date_formats = [
                        '%Y-%m-%dT%H:%M',
                        '%Y-%m-%d %H:%M',
                        '%d/%m/%Y %H:%M',
                        '%d/%m/%Y'
                    ]
                    
                    for fmt in date_formats:
                        try:
                            due_date = datetime.strptime(due_part, fmt).isoformat()
                            break
                        except:
                            continue
                    
                    if not due_date:
                        # If none matched, try ISO format
                        due_date = due_part
                except:
                    due_date = None
        
        result = task_manager.create_task(
            user_id=user_id,
            description=description,
            due_date=due_date,
            category=category,
            priority=priority
        )
        
        response = result.get("message", "✅ המשימה נוצרה בהצלחה!")
        
        if result.get("reminder"):
            response += f"\n⏰ תזכורת תישלח ב: {result['reminder']}"
        
        update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
        
    elif subcommand == "list":
        # List tasks
        category = context.args[1] if len(context.args) > 1 else None
        tasks = task_manager.list_tasks(user_id, category)
        
        if not tasks:
            update.message.reply_text(
                "📭 *אין משימות פעילות* \n\n"
                "צור משימה חדשה עם `/task new <תיאור>`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        tasks_text = f"📋 *רשימת משימות ({len(tasks)})*\n\n"
        
        for task in tasks:
            task_id = task['id']
            description = task['description']
            category = task.get('category', 'כללי')
            priority = task.get('priority', 'medium')
            due_date = task.get('due_date')
            
            # Priority emojis
            priority_emoji = {
                'high': '🔴',
                'medium': '🟡', 
                'low': '🟢'
            }.get(priority, '⚪')
            
            tasks_text += f"{priority_emoji} *משימה #{task_id}:* {description}\n"
            tasks_text += f"   🏷️ קטגוריה: {category}\n"
            
            if due_date:
                try:
                    due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                    due_str = due_dt.strftime("%d/%m/%Y %H:%M")
                    tasks_text += f"   ⏰ תאריך יעד: {due_str}\n"
                except:
                    tasks_text += f"   ⏰ תאריך יעד: {due_date}\n"
            
            tasks_text += f"   ✅ השלמה: `/task complete {task_id}`\n\n"
        
        tasks_text += f"_סה״כ: {len(tasks)} משימות פעילות_"
        
        update.message.reply_text(tasks_text, parse_mode=ParseMode.MARKDOWN)
        
    elif subcommand == "complete" and len(context.args) > 1:
        # Complete task
        try:
            task_id = int(context.args[1])
            result = task_manager.complete_task(user_id, task_id)
            
            if result.get("success"):
                update.message.reply_text(
                    result.get("message", "✅ המשימה הושלמה!"),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                update.message.reply_text(
                    f"❌ {result.get('error', 'שגיאה בהשלמת המשימה')}",
                    parse_mode=ParseMode.MARKDOWN
                )
        except ValueError:
            update.message.reply_text(
                "❌ *מספר משימה לא תקין*\n\n"
                "שימוש: `/task complete <מספר>`\n"
                "לדוגמה: `/task complete 5`",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif subcommand == "stats":
        # Task statistics
        stats = task_manager.get_statistics(user_id)
        
        stats_text = (
            f"📊 *סטטיסטיקות משימות - {update.effective_user.first_name}*\n\n"
            f"*סיכום:*\n"
            f"• 📝 סך הכל: {stats['total']}\n"
            f"• ✅ הושלמו: {stats['completed']}\n"
            f"• ⏳ ממתינות: {stats['pending']}\n"
            f"• 📈 שיעור השלמה: {stats['completion_rate']}%\n\n"
        )
        
        # By category
        if stats['by_category']:
            stats_text += "*לפי קטגוריה:*\n"
            for category, count in sorted(stats['by_category'].items(), 
                                        key=lambda x: x[1], reverse=True)[:5]:
                stats_text += f"• {category}: {count}\n"
        
        # By priority
        stats_text += "\n*לפי עדיפות:*\n"
        for priority in ['high', 'medium', 'low']:
            count = stats['by_priority'].get(priority, 0)
            if count > 0:
                emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}[priority]
                hebrew_priority = {'high': 'גבוהה', 'medium': 'בינונית', 'low': 'נמוכה'}[priority]
                stats_text += f"• {emoji} {hebrew_priority}: {count}\n"
        
        # Completion streak (simplified)
        completed_tasks = [t for t in tasks_db 
                          if t['user_id'] == user_id and t.get('completed')]
        
        if completed_tasks:
            # Count tasks completed today
            today = datetime.now().date()
            today_count = len([t for t in completed_tasks 
                             if datetime.fromisoformat(
                                 t.get('completed_date', '2000-01-01').replace('Z', '+00:00')
                             ).date() == today])
            
            if today_count > 0:
                stats_text += f"\n🎯 *היום:* השלמת {today_count} משימות!\n"
        
        stats_text += f"\n_נכון ל: {datetime.now().strftime('%d/%m/%Y %H:%M')}_"
        
        update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
    
    else:
        update.message.reply_text(
            "❓ *שימוש לא תקין בפקודת task*\n\n"
            "השתמש ב `/task` ללא פרמטרים לראות את כל האפשרויות.",
            parse_mode=ParseMode.MARKDOWN
        )

def trivia_command(update, context):
    """Send a random trivia question"""
    log_message(update, 'trivia')
    
    # Get random trivia question
    trivia_questions = quiz_system.quizzes.get("trivia", [])
    
    if not trivia_questions:
        update.message.reply_text(
            "❌ *אין שאלות טריוויה זמינות כרגע*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    question = random.choice(trivia_questions)
    question_index = trivia_questions.index(question)
    
    # Format question
    trivia_text = f"❓ *שאלת טריוויה:*\n\n{question['question']}\n\n"
    
    letters = ['א', 'ב', 'ג', 'ד']
    for i, option in enumerate(question['options']):
        trivia_text += f"{letters[i]}. {option}\n"
    
    trivia_text += f"\n🎯 *נקודות:* {question['points']}\n\n"
    trivia_text += "*השתמש ב:* `/answer <מספר>` כדי לענות\n"
    trivia_text += "*לדוגמה:* `/answer 0` עבור תשובה א"
    
    # Store question in context for answer checking
    context.user_data['trivia_question'] = {
        'question': question,
        'question_index': question_index,
        'timestamp': datetime.now().isoformat()
    }
    
    update.message.reply_text(trivia_text, parse_mode=ParseMode.MARKDOWN)

def answer_command(update, context):
    """Answer a trivia question"""
    log_message(update, 'answer')
    
    if 'trivia_question' not in context.user_data:
        update.message.reply_text(
            "❌ *אין שאלה פעילה לענות עליה*\n\n"
            "השתמש ב `/trivia` כדי לקבל שאלה חדשה.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if not context.args:
        update.message.reply_text(
            "❌ *צריך לציין מספר תשובה*\n\n"
            "שימוש: `/answer <מספר>`\n"
            "מספרים: 0=א, 1=ב, 2=ג, 3=ד\n\n"
            "לדוגמה: `/answer 0`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        answer_index = int(context.args[0])
        question_data = context.user_data['trivia_question']
        question = question_data['question']
        
        # Check if answer is within range
        if answer_index < 0 or answer_index >= len(question['options']):
            update.message.reply_text(
                f"❌ *מספר תשובה לא תקין*\n\n"
                f"אפשרויות: 0-{len(question['options'])-1}\n"
                f"0=א, 1=ב, 2=ג, 3=ד",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        is_correct = (answer_index == question['correct'])
        
        # Clear the stored question
        del context.user_data['trivia_question']
        
        # Prepare response
        letters = ['א', 'ב', 'ג', 'ד']
        correct_letter = letters[question['correct']]
        correct_answer = question['options'][question['correct']]
        
        if is_correct:
            response_text = (
                f"🎉 *נכון! תשובה מצוינת!*\n\n"
                f"✅ התשובה הנכונה היא אכן {correct_letter}. {correct_answer}\n\n"
                f"🏆 זכית ב-{question['points']} נקודות!"
            )
            
            # Update user score
            user_id = update.effective_user.id
            if str(user_id) not in quiz_scores_db:
                quiz_scores_db[str(user_id)] = []
            
            quiz_scores_db[str(user_id)].append({
                "game_id": f"trivia_{int(time.time())}",
                "quiz_type": "trivia",
                "score": question['points'],
                "total_possible": question['points'],
                "date": datetime.now().isoformat(),
                "answers": [{
                    "question_index": question_data['question_index'],
                    "answer": answer_index,
                    "correct": question['correct'],
                    "is_correct": True,
                    "points": question['points']
                }]
            })
            
            save_json(QUIZ_FILE, quiz_scores_db)
            
        else:
            user_letter = letters[answer_index]
            user_answer = question['options'][answer_index]
            
            response_text = (
                f"❌ *לא נכון, אבל נסיון טוב!*\n\n"
                f"התשובה שלך ({user_letter}. {user_answer}) אינה נכונה.\n\n"
                f"✅ התשובה הנכונה היא {correct_letter}. {correct_answer}\n\n"
                f"💡 נסה שוב עם שאלה חדשה: `/trivia`"
            )
        
        update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
        
    except ValueError:
        update.message.reply_text(
            "❌ *מספר לא תקין*\n\n"
            "הקלד מספר בין 0-3\n"
            "0=א, 1=ב, 2=ג, 3=ד",
            parse_mode=ParseMode.MARKDOWN
        )

def profile_command(update, context):
    """Show user profile with enhanced statistics"""
    log_message(update, 'profile')
    
    user = update.effective_user
    user_id = user.id
    
    # Get user record
    user_record = next((u for u in users_db if u['user_id'] == user_id), None)
    
    if not user_record:
        user_record = get_or_create_user({
            'id': user_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }, 'private')
    
    # Calculate statistics
    total_messages = user_record.get('message_count', 0)
    engagement = user_record.get('stats', {}).get('engagement_score', 0.5) * 100
    
    # Get favorite commands
    commands_used = user_record.get('stats', {}).get('commands_used', {})
    favorite_commands = sorted(commands_used.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # Get quiz stats
    quiz_stats = quiz_scores_db.get(str(user_id), [])
    total_quiz_score = sum(q.get('score', 0) for q in quiz_stats)
    quiz_games = len(quiz_stats)
    avg_quiz_score = total_quiz_score / quiz_games if quiz_games > 0 else 0
    
    # Get task stats
    user_tasks = [t for t in tasks_db if t['user_id'] == user_id]
    completed_tasks = len([t for t in user_tasks if t.get('completed')])
    
    # Calculate level based on activity
    activity_score = (total_messages * 0.1) + (total_quiz_score * 0.2) + (completed_tasks * 5)
    level = min(100, int(activity_score ** 0.5) + 1)
    xp_needed = ((level + 1) ** 2) - (level ** 2)
    xp_current = activity_score - (level ** 2)
    progress_percent = (xp_current / xp_needed * 100) if xp_needed > 0 else 100
    
    # Build profile text
    profile_text = (
        f"👤 *פרופיל משתמש - {user.first_name}*\n\n"
        f"*פרטים אישיים:*\n"
        f"• 🆔 מזהה: `{user_id}`\n"
        f"• 📛 משתמש: @{user.username or 'ללא'}\n"
        f"• 📅 הצטרף: {datetime.fromisoformat(user_record['first_seen']).strftime('%d/%m/%Y')}\n"
        f"• ⭐ רמה: {level}\n"
        f"• 📈 התקדמות: {progress_percent:.1f}% לרמה {level + 1}\n\n"
    )
    
    # Activity stats
    profile_text += f"*סטטיסטיקות פעילות:*\n"
    profile_text += f"• 💬 הודעות: {total_messages}\n"
    profile_text += f"• 🎮 משחקי quiz: {quiz_games}\n"
    profile_text += f"• 📝 משימות: {len(user_tasks)} ({completed_tasks} הושלמו)\n"
    profile_text += f"• 📊 מעורבות: {engagement:.1f}%\n\n"
    
    # Quiz performance
    if quiz_games > 0:
        profile_text += f"*ביצועי Quiz:*\n"
        profile_text += f"• 🏆 ניקוד כולל: {total_quiz_score}\n"
        profile_text += f"• ⭐ ממוצע: {avg_quiz_score:.1f}\n\n"
    
    # Favorite features
    if favorite_commands:
        profile_text += f"*תכונות מועדפות:*\n"
        for cmd, count in favorite_commands:
            cmd_name = {
                'start': 'התחלה',
                'help': 'עזרה',
                'stock': 'מניות',
                'quiz': 'משחק',
                'trivia': 'טריוויה',
                'task': 'משימות'
            }.get(cmd, cmd)
            profile_text += f"• {cmd_name}: {count} פעמים\n"
    
    # Task completion rate
    if user_tasks:
        completion_rate = (completed_tasks / len(user_tasks) * 100) if user_tasks else 0
        profile_text += f"• ✅ השלמת משימות: {completion_rate:.1f}%\n"
    
    # User level visual
    profile_text += f"\n*🎯 רמת משתמש:* {'⭐' * min(5, level // 10)}\n"
    
    # DNA learning insights
    user_patterns = advanced_dna.learning_data.get("user_patterns", {}).get(str(user_id), {})
    if user_patterns.get("activity_times"):
        peak_hour = max(set(user_patterns["activity_times"]), 
                       key=user_patterns["activity_times"].count)
        profile_text += f"• 🕐 שעת פעילות שיא: {peak_hour}:00\n"
    
    profile_text += f"\n_עודכן: {datetime.now().strftime('%H:%M')}_"
    
    # Add achievement badges
    achievements = []
    
    if total_messages >= 100:
        achievements.append("💬 צ'אטיסט")
    if quiz_games >= 10:
        achievements.append("🎯 אלוף Quiz")
    if completed_tasks >= 20:
        achievements.append("✅ משלים משימות")
    if level >= 10:
        achievements.append("⭐ ותיק")
    if engagement >= 80:
        achievements.append("📊 פעיל מאוד")
    
    if achievements:
        profile_text += f"\n*🏅 הישגים:* {' '.join(achievements)}"
    
    update.message.reply_text(profile_text, parse_mode=ParseMode.MARKDOWN)

# ==================== ENHANCED BOT COMMANDS ====================
def start(update, context):
    """Enhanced start command"""
    log_message(update, 'start')
    user = update.effective_user
    chat = update.effective_chat
    
    # Record DNA learning
    advanced_dna._analyze_user_pattern(user.id, 'start', {'chat_type': chat.type})
    
    # Different welcome for groups vs private
    if chat.type == 'private':
        welcome_text = (
            f"👋 *ברוך הבא {user.first_name}!*\n\n"
            f"🤖 *אני {BOT_NAME}, הבוט המתפתח שלך!*\n\n"
            f"🚀 *מה אני יכול לעשות?*\n"
            f"• 📈 ניתוח מניות ומידע פיננסי\n"
            f"• 🎮 משחקי quiz וטריוויה\n"
            f"• 📝 ניהול משימות ותזכורות\n"
            f"• 📊 סטטיסטיקות וניתוח נתונים\n"
            f"• 🧬 מערכת DNA אבולוציונית מתקדמת\n\n"
            f"🔄 *הבוט שלי מתפתח ומשתפר אוטומטית* \n"
            f"בהתבסס על השימוש שלך ושל אחרים!\n\n"
            f"📋 *השתמש בתפריט למטה או בפקודות:*\n"
            f"/help - רשימת פקודות\n"
            f"/menu - תפריט כפתורים\n"
            f"/features - תכונות מיוחדות\n"
            f"/dna - מערכת ה-DNA של הבוט\n"
        )
        
        if is_admin(user.id):
            welcome_text += "\n👑 *גישה למנהל זוהתה!*\nהשתמש בתפריט המנהל או ב-/admin"
        
        update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user.id)
        )
    else:
        # Group welcome
        welcome_text = (
            f"👋 *שלום לכולם!*\n\n"
            f"🤖 *אני {BOT_NAME} כאן לעזור לכם!*\n\n"
            f"📍 *כדי להשתמש בי בקבוצה:*\n"
            f"1. הזכירו אותי עם @{BOT_USERNAME}\n"
            f"2. או השתמשו בפקודות ישירות\n"
            f"3. או לחצו על הכפתורים למטה\n\n"
            f"🎯 *תכונות מיוחדות לקבוצות:*\n"
            f"• 🎮 quiz קבוצתי\n"
            f"• 📊 סטטיסטיקות קבוצה\n"
            f"• ⏰ תזכורות משותפות\n\n"
            f"📌 *דוגמאות:*\n"
            f"`@{BOT_USERNAME} סטטוס`\n"
            f"`@{BOT_USERNAME} quiz`\n"
            f"/help@{BOT_USERNAME}"
        )
        
        update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_group_keyboard()
        )

def help_command(update, context):
    """Enhanced help command"""
    log_message(update, 'help')
    chat = update.effective_chat
    
    if chat.type == 'private':
        help_text = (
            "📚 *רשימת פקודות מלאה - בוט מתפתח*\n\n"
            "🔹 *פקודות בסיסיות:*\n"
            "/start - הודעת פתיחה\n"
            "/help - רשימת פקודות זו\n"
            "/menu - תפריט כפתורים\n"
            "/profile - הפרופיל שלך\n"
            "/id - הצג את ה-ID שלך\n"
            "/info - סטטיסטיקות בוט\n"
            "/ping - בדיקת חיים\n\n"
            "💰 *פיננסים ומניות:*\n"
            "/stock <סימבול> - מחיר מניה\n"
            "/analyze <סימבול> - ניתוח מניה\n"
            "/exchange <מ> <אל> - שער חליפין\n"
            "/economic - אירועים כלכליים\n\n"
            "🎮 *משחקים ובידור:*\n"
            "/quiz - התחלת משחק quiz\n"
            "/trivia - שאלת טריוויה\n"
            "/leaderboard - טבלת שיאים\n"
            "/answer <מספר> - תשובה לטריוויה\n\n"
            "📝 *משימות ופרודוקטיביות:*\n"
            "/task - ניהול משימות\n"
            "/task new <תיאור> - משימה חדשה\n"
            "/task list - רשימת משימות\n"
            "/task stats - סטטיסטיקות\n\n"
            "🧬 *אבולוציה ו-DNA:*\n"
            "/dna - מערכת DNA\n"
            "/evolve - ניהול אבולוציה\n"
            "/lineage - שושלת מודולים\n\n"
            "👑 *פקודות מנהל:*\n"
            "/admin - לוח בקרה\n"
            "/stats - סטטיסטיקות מפורטות\n"
            "/broadcast - שידור לכולם\n"
            "/users - ניהול משתמשים\n\n"
            "💡 *בקבוצות:*\n"
            f"הזכירו אותי עם @{BOT_USERNAME}\n"
            "או השתמשו בפקודות ישירות\n\n"
            "⚙️ *הבוט מתפתח אוטומטית* בהתבסס על השימוש שלך!"
        )
    else:
        help_text = (
            f"🤖 *פקודות זמינות בקבוצה:*\n\n"
            f"📍 *הזכירו אותי עם @{BOT_USERNAME}* או השתמשו בפקודות:\n\n"
            f"`@{BOT_USERNAME} סטטוס` - מצב הבוט\n"
            f"`@{BOT_USERNAME} מידע` - מידע על הבוט\n"
            f"`@{BOT_USERNAME} עזרה` - הודעה זו\n"
            f"`@{BOT_USERNAME} id` - הצג ID\n"
            f"`@{BOT_USERNAME} quiz` - התחלת quiz\n"
            f"`@{BOT_USERNAME} trivia` - שאלת טריוויה\n\n"
            f"📌 *פקודות ישירות:*\n"
            f"/help@{BOT_USERNAME} - עזרה\n"
            f"/about@{BOT_USERNAME} - אודות\n"
            f"/info@{BOT_USERNAME} - סטטיסטיקות\n"
            f"/quiz@{BOT_USERNAME} - משחק quiz\n\n"
            f"💡 *טיפ:* השתמשו בכפתורים למטה לנוחות!"
        )
    
    try:
        update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error sending help: {e}")
        plain_text = help_text.replace('*', '').replace('`', '').replace('_', '')
        update.message.reply_text(plain_text)

def features_command(update, context):
    """Show special features"""
    log_message(update, 'features')
    
    # Get DNA capabilities
    dna_caps = advanced_dna.dna.get("capabilities", {})
    enabled_features = [k for k, v in dna_caps.items() if v]
    
    features_text = (
        f"🌟 *תכונות מיוחדות - {BOT_NAME}*\n\n"
        f"🤖 *הבוט שלי מתפתח ומשתפר אוטומטית!*\n\n"
        f"🔧 *יכולות מופעלות:*\n"
    )
    
    # Add enabled capabilities
    if enabled_features:
        feature_emojis = {
            'nlp': '💬',
            'prediction': '🔮', 
            'automation': '⚙️',
            'integration': '🔗',
            'learning': '🧠'
        }
        
        for feature in enabled_features:
            emoji = feature_emojis.get(feature, '✅')
            hebrew_name = {
                'nlp': 'עיבוד שפה טבעית',
                'prediction': 'חיזוי וניתוח',
                'automation': 'אוטומציה',
                'integration': 'אינטגרציה',
                'learning': 'למידה מתמדת'
            }.get(feature, feature)
            features_text += f"{emoji} {hebrew_name}\n"
    
    features_text += "\n🎯 *תכונות מיוחדות פעילות:*\n"
    
    # Financial features
    if ALPHAVANTAGE_API_KEY:
        features_text += "• 💹 ניתוח מניות ופיננסים\n"
    
    # Quiz system
    features_text += "• 🎮 מערכת quiz וטריוויה\n"
    
    # Task management
    features_text += "• 📝 ניהול משימות ותזכורות\n"
    
    # Evolution system
    features_text += "• 🧬 DNA אבולוציוני מתקדם\n"
    
    # Learning system
    features_text += "• 📊 ניתוח דפוסי משתמשים\n"
    
    features_text += "\n🚀 *בפיתוח עתידי:*\n"
    features_text += "• 🤖 אינטליגנציה מלאכותית מתקדמת\n"
    features_text += "• 📈 חיזוי מגמות\n"
    features_text += "• 👥 ניהול קהילות\n"
    features_text += "• 🎯 המלצות מותאמות אישית\n"
    
    # Evolution progress
    report = advanced_dna.get_evolution_report()
    progress = report["progress"]
    
    features_text += f"\n🧬 *התקדמות אבולוציה:* {progress['percent']:.1f}%\n"
    features_text += f"📈 *רמת התפתחות:* {progress['level']}\n"
    
    # User's contribution to evolution
    user_id = update.effective_user.id
    user_patterns = advanced_dna.learning_data.get("user_patterns", {}).get(str(user_id), {})
    if user_patterns.get("command_frequency"):
        total_commands = sum(user_patterns["command_frequency"].values())
        features_text += f"\n📊 *התרומה שלך:* {total_commands} אינטראקציות"
    
    features_text += f"\n\n_עודכן: {datetime.now().strftime('%H:%M')}_"
    
    update.message.reply_text(features_text, parse_mode=ParseMode.MARKDOWN)

def menu_command(update, context):
    """Enhanced menu command"""
    log_message(update, 'menu')
    user = update.effective_user
    
    # Get user's favorite features
    user_record = next((u for u in users_db if u['user_id'] == user.id), None)
    favorite_features = []
    
    if user_record and user_record.get('stats', {}).get('favorite_features'):
        favorite_features = user_record['stats']['favorite_features'][:3]
    
    menu_text = (
        f"📱 *תפריט ראשי מתקדם - {BOT_NAME}*\n\n"
        f"👤 *ברוך הבא {user.first_name}!*\n\n"
        f"🔹 *בחר אפשרות מהתפריט למטה:*\n\n"
    )
    
    # Personalized recommendations
    if favorite_features:
        menu_text += f"⭐ *מומלץ עבורך:*\n"
        feature_names = {
            'stock': '📈 מניות',
            'quiz': '🎮 quiz',
            'task': '📝 משימות', 
            'trivia': '❓ טריוויה',
            'exchange': '💱 מטבעות'
        }
        
        for feature in favorite_features:
            if feature in feature_names:
                menu_text += f"• {feature_names[feature]}\n"
        menu_text += "\n"
    
    menu_text += (
        f"📊 *מידע וסטטיסטיקות:*\n"
        f"• סטטיסטיקות - נתוני שימוש\n"
        f"• מידע על הבוט - מהות ותכונות\n"
        f"• הפרופיל שלי - נתונים אישיים\n\n"
        
        f"💼 *פיננסים:*\n"
        f"• מניות - מחירים וניתוח\n"
        f"• שערי חליפין - המרת מטבעות\n"
        f"• אירועים כלכליים - לוח שנה\n\n"
        
        f"🎮 *משחקים:*\n"
        f"• quiz - משחק ידע\n"
        f"• טריוויה - שאלה יומית\n"
        f"• טבלת שיאים - תחרות\n\n"
        
        f"📝 *פרודוקטיביות:*\n"
        f"• משימות - ניהול מטלות\n"
        f"• תזכורות - התראות\n\n"
        
        f"🧬 *אבולוציה:*\n"
        f"• DNA - מערכת אבולוציונית\n"
        f"• תכונות מיוחדות - יכולות מתקדמות\n"
    )
    
    if is_admin(user.id):
        menu_text += f"\n👑 *תפריט מנהל:*\n• תפריט מנהל - כלי ניהול מתקדמים\n"
    
    menu_text += f"\n📍 *או השתמש בפקודות מהרשימה המלאה ב /help*"
    
    update.message.reply_text(
        menu_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(user.id)
    )

def bot_info(update, context):
    """Enhanced bot info command"""
    log_message(update, 'info')
    
    stats = bot_stats.get_summary()
    dna_report = advanced_dna.get_evolution_report()
    
    # Calculate response time estimate
    message_rate = stats['total_messages'] / max(1, bot_stats.stats['uptime_seconds'] / 3600)
    avg_response = "מהיר מאוד" if message_rate < 10 else "מהיר" if message_rate < 50 else "בינוני"
    
    info_text = (
        f"📊 *סטטיסטיקות מתקדמות - {BOT_NAME}*\n\n"
        f"🤖 *פרטי הבוט:*\n"
        f"• 🏷️ שם: {BOT_NAME}\n"
        f"• 🆔 ID: `{BOT_ID}`\n"
        f"• 👤 משתמש: @{BOT_USERNAME}\n"
        f"• 🧬 דור: {dna_report['dna_info']['generation']}\n"
        f"• ⭐ דירוג התאמה: {dna_report['dna_info']['fitness_score']}/100\n\n"
        
        f"📈 *פעילות מערכת:*\n"
        f"• ⏱️ זמן פעילות: {stats['uptime']}\n"
        f"• 📨 הודעות שקיבל: {stats['total_messages']}\n"
        f"• 📊 קצב הודעות: {message_rate:.1f}/שעה\n"
        f"• 👥 משתמשים ייחודיים: {stats['total_users']}\n"
        f"• 👥 משתמשים פעילים: {stats['active_users']}\n"
        f"• 👥 קבוצות פעילות: {len(bot_stats.stats['groups'])}\n"
        f"• 🚀 פקודות /start: {stats['start_count']}\n"
        f"• 📝 פקודות סה״כ: {stats['commands_count']}\n"
        f"• ⚡ תגובה: {avg_response}\n\n"
    )
    
    # Top features
    if stats['top_commands']:
        info_text += f"⭐ *תכונות פופולריות:*\n"
        for cmd, count in stats['top_commands'][:3]:
            cmd_name = {
                'start': 'התחלה',
                'help': 'עזרה',
                'stock': 'מניות',
                'quiz': 'Quiz',
                'trivia': 'טריוויה',
                'task': 'משימות',
                'dna': 'DNA'
            }.get(cmd, cmd)
            info_text += f"• {cmd_name}: {count}\n"
    
    # System health
    error_rate = (stats['errors_count'] / max(1, stats['total_messages'])) * 100
    health_status = "מצוין" if error_rate < 1 else "טוב" if error_rate < 5 else "דורש תשומת לב"
    
    info_text += f"\n🏥 *בריאות מערכת:* {health_status}\n"
    info_text += f"• ❌ שגיאות: {stats['errors_count']} ({error_rate:.2f}%)\n"
    
    # Evolution status
    progress = dna_report["progress"]
    info_text += f"• 🧬 התפתחות: {progress['level']} ({progress['percent']:.1f}%)\n"
    
    # Platform info
    info_text += f"\n🏗️ *פלטפורמה:* Railway\n"
    info_text += f"• 🔗 Webhook: {'פעיל ✅' if WEBHOOK_URL else 'לא מוגדר'}\n"
    info_text += f"• 🛡️ אבטחה: {'מאובטח ✅' if WEBHOOK_SECRET else 'בסיסי'}\n"
    info_text += f"• 📅 התחלה: {datetime.fromisoformat(bot_stats.stats['start_time']).strftime('%d/%m/%Y %H:%M')}\n"
    
    info_text += f"\n_עודכן: {datetime.now().strftime('%H:%M')}_"
    
    update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)

def ping(update, context):
    """Enhanced ping command"""
    log_message(update, 'ping')
    
    # Calculate response time
    start_time = time.time()
    message = update.message.reply_text("🏓 *בודק תגובת שרת...*", parse_mode=ParseMode.MARKDOWN)
    response_time = (time.time() - start_time) * 1000
    
    # Get system stats
    stats = bot_stats.get_summary()
    dna_report = advanced_dna.get_evolution_report()
    
    ping_text = (
        f"🏓 *פונג! הבוט חי ותקין*\n\n"
        f"✅ *בריאות מערכת:*\n"
        f"• ⚡ זמן תגובה: {response_time:.0f}ms\n"
        f"• 🖥️ עובדים: {dispatcher.workers}\n"
        f"• 💾 משתמשים בזיכרון: {len(users_db)}\n"
        f"• 📡 Webhook: {'פעיל' if WEBHOOK_URL else 'לא פעיל'}\n\n"
        
        f"📊 *מטען מערכת:*\n"
        f"• 📨 הודעות/שעה: {stats['total_messages'] / max(1, bot_stats.stats['uptime_seconds'] / 3600):.1f}\n"
        f"• 👥 משתמשים פעילים: {stats['active_users']}\n"
        f"• 📝 פקודות אחרונות: {stats['commands_count']}\n\n"
        
        f"🧬 *מצב אבולוציה:*\n"
        f"• ⭐ דירוג: {dna_report['dna_info']['fitness_score']}/100\n"
        f"• 📈 רמה: {dna_report['progress']['level']}\n"
        f"• 🔄 מוטציות: {dna_report['dna_info']['total_mutations']}\n\n"
        
        f"🤖 *פרטי מערכת:*\n"
        f"• שם: {BOT_NAME}\n"
        f"• ID: `{BOT_ID}`\n"
        f"• משתמש: @{BOT_USERNAME}\n"
        f"• סביבה: {'Production' if WEBHOOK_URL else 'Development'}"
    )
    
    # Check if response is slow
    if response_time > 1000:
        ping_text += f"\n\n⚠️ *הערה:* זמן תגובה איטי, יתכן עומס על השרת"
    
    message.edit_text(ping_text, parse_mode=ParseMode.MARKDOWN)

# ==================== CALLBACK QUERY HANDLER ====================
def button_callback(update, context):
    """Handle inline button callbacks"""
    query = update.callback_query
    query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    logger.info(f"Button callback: {data} from user {user_id}")
    
    # Quiz answer handling
    if data.startswith("quiz_answer_"):
        parts = data.split("_")
        if len(parts) >= 4:
            game_id = parts[2]
            answer_index = int(parts[3])
            
            # Process answer
            result = quiz_system.answer_question(game_id, answer_index)
            
            if result.get("success"):
                response = result.get("explanation", "")
                
                if result.get("completed"):
                    score = result.get("total_score", 0)
                    response += f"\n\n🎉 *Quiz הושלם!*\n"
                    response += f"🏆 *ניקוד סופי:* {score} נקודות\n\n"
                    response += f"🎮 משחק חדש: /quiz\n"
                    response += f"🏆 טבלת שיאים: /leaderboard"
                else:
                    # Show next question or continue
                    response += f"\n\n📊 *ניקוד נוכחי:* {result['total_score']}\n"
                    response += f"➡️ *שאלה הבאה:* לחץ שוב על תשובה"
                
                query.edit_message_text(response, parse_mode=ParseMode.MARKDOWN)
            else:
                query.edit_message_text(
                    f"❌ שגיאה: {result.get('error', 'Unknown error')}",
                    parse_mode=ParseMode.MARKDOWN
                )
    
    # Quiz start handling
    elif data.startswith("quiz_start_"):
        quiz_type = data.split("_")[2]
        user_id = query.from_user.id
        
        result = quiz_system.start_quiz(user_id, quiz_type)
        
        if result.get("success"):
            game_id = result["game_id"]
            first_question = result["first_question"]
            
            # Create answer buttons
            keyboard = []
            letters = ['א', 'ב', 'ג', 'ד']
            for i, letter in enumerate(letters):
                keyboard.append([InlineKeyboardButton(
                    f"{letter}", 
                    callback_data=f"quiz_answer_{game_id}_{i}"
                )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            quiz_text = (
                f"🎮 *Quiz התחיל!*\n"
                f"*סוג:* {quiz_type}\n"
                f"*מספר שאלות:* {result['question_count']}\n\n"
                f"{first_question}\n\n"
                f"*לחץ על הכפתור עם התשובה הנכונה:*"
            )
            
            query.edit_message_text(
                quiz_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    
    # Other button types can be added here
    else:
        query.edit_message_text(
            f"❓ *כפתור לא מזוהה*\n\n"
            f"הפעולה המבוקשת אינה זמינה כרגע.",
            parse_mode=ParseMode.MARKDOWN
        )

# ==================== ENHANCED TEXT HANDLER ====================
def handle_text(update, context):
    """Enhanced text message handler"""
    message = update.message
    if not message or not message.text:
        return
    
    # Check if we should respond
    if not should_respond(update):
        return
    
    log_message(update, 'text')
    user = update.effective_user
    chat = update.effective_chat
    
    text = message.text.lower()
    
    # Handle button presses
    if text == "📊 סטטיסטיקות":
        bot_info(update, context)
    
    elif text == "ℹ️ מידע על הבוט":
        about_command(update, context)
    
    elif text == "🧩 תכונות חדשות":
        features_command(update, context)
    
    elif text == "🎮 משחק":
        quiz_command(update, context)
    
    elif text == "📈 מניות":
        update.message.reply_text(
            "💹 *תפריט מניות ופיננסים:*\n\n"
            "השתמש בפקודות:\n"
            "`/stock <סימבול>` - מחיר מניה\n"
            "`/analyze <סימבול>` - ניתוח מפורט\n"
            "`/exchange <מ> <אל>` - שער חליפין\n\n"
            "*דוגמאות:*\n"
            "`/stock AAPL` - מחיר אפל\n"
            "`/exchange USD ILS` - דולר לשקל",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_financial_keyboard()
        )
    
    elif text == "👤 הפרופיל שלי":
        profile_command(update, context)
    
    elif text == "📝 משימות":
        task_command(update, context)
    
    elif text == "❓ עזרה":
        help_command(update, context)
    
    elif text == "🔄 רענן":
        update.message.reply_text("🔄 *תפריט רענן!*", parse_mode=ParseMode.MARKDOWN)
        menu_command(update, context)
    
    elif text == "👑 ניהול" and is_admin(user.id):
        admin_panel(update, context)
    
    elif text == "⚙️ הגדרות מתקדמות" and is_admin(user.id):
        update.message.reply_text(
            f"⚙️ *הגדרות מתקדמות - {BOT_NAME}*\n\n"
            f"🔧 *פעולות מנהל:*\n"
            "• הגדרת Webhook: `/setwebhook <url>`\n"
            "• בדיקת מערכת: `/system_check`\n"
            "• ניהול זיכרון: `/memory_status`\n"
            "• בדיקת חיבורים: `/connection_test`\n\n"
            f"📊 *מצב נוכחי:*\n"
            f"• Webhook: {'מוגדר ✅' if WEBHOOK_URL else 'לא מוגדר'}\n"
            f"• סוד Webhook: {'מוגדר ✅' if WEBHOOK_SECRET else 'לא מוגדר'}\n"
            f"• מנהל: {ADMIN_USER_ID}\n"
            f"• API מניות: {'פעיל ✅' if ALPHAVANTAGE_API_KEY else 'לא מוגדר'}\n\n"
            f"💾 *מאגר נתונים:*\n"
            f"• משתמשים: {len(users_db)}\n"
            f"• קבוצות: {len(groups_db)}\n"
            f"• הודעות: {len(messages_db)}\n"
            f"• משימות: {len(tasks_db)}\n",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Handle group mentions
    elif BOT_USERNAME and f"@{BOT_USERNAME}" in message.text:
        mentioned_text = message.text.lower()
        
        if "סטטוס" in mentioned_text or "status" in mentioned_text:
            stats = bot_stats.get_summary()
            
            update.message.reply_text(
                f"🤖 *סטטוס {BOT_NAME}:*\n"
                f"✅ פעיל וזמין\n"
                f"📊 {stats['total_messages']} הודעות\n"
                f"👥 {stats['total_users']} משתמשים\n"
                f"🎮 {len(quiz_scores_db)} משחקי quiz\n"
                f"🆔 ID: `{BOT_ID}`\n\n"
                f"_לפקודות מלאות: @{BOT_USERNAME} עזרה_",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif "מידע" in mentioned_text or "info" in mentioned_text:
            about_command(update, context)
        
        elif "עזרה" in mentioned_text or "help" in mentioned_text:
            help_command(update, context)
        
        elif "id" in mentioned_text or "מספר" in mentioned_text:
            show_id(update, context)
        
        elif "quiz" in mentioned_text or "משחק" in mentioned_text:
            quiz_command(update, context)
        
        elif "trivia" in mentioned_text or "טריוויה" in mentioned_text:
            trivia_command(update, context)
        
        elif "stock" in mentioned_text or "מניה" in mentioned_text:
            update.message.reply_text(
                f"📈 *מידע מניות:*\n\n"
                f"השתמש ב: `/stock <סימבול>`\n\n"
                f"*דוגמה:* `/stock AAPL`\n"
                f"*דוגמה נוספת:* `/stock TSLA`\n\n"
                f"לעזרה נוספת: @{BOT_USERNAME} עזרה",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif "בוט" in mentioned_text or "רובוט" in mentioned_text:
            update.message.reply_text(
                f"🤖 *כן, אני {BOT_NAME}!*\n\n"
                f"אני בוט מתפתח עם יכולות מתקדמות:\n"
                f"• 📈 ניתוח מניות\n"
                f"• 🎮 משחקי quiz\n"
                f"• 📝 ניהול משימות\n"
                f"• 🧬 מערכת DNA אבולוציונית\n\n"
                f"השתמש ב @{BOT_USERNAME} עזרה כדי לראות את כל הפקודות.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        else:
            update.message.reply_text(
                f"🤖 *היי, אני {BOT_NAME}!*\n\n"
                f"נכתב: {message.text[:100]}...\n\n"
                f"📌 *ניתן לבקש ממני:*\n"
                f"`@{BOT_USERNAME} סטטוס` - מצב הבוט\n"
                f"`@{BOT_USERNAME} עזרה` - רשימת פקודות\n"
                f"`@{BOT_USERNAME} quiz` - משחק quiz\n"
                f"`@{BOT_USERNAME} trivia` - שאלת טריוויה\n\n"
                f"לכל הפקודות: /help@{BOT_USERNAME}\n"
                f"🆔 *ID הבוט שלי:* `{BOT_ID}`",
                parse_mode=ParseMode.MARKDOWN
            )
    
    # Default echo for private chats with learning
    elif chat.type == 'private':
        # Analyze user message
        user_id = user.id
        advanced_dna._analyze_user_pattern(user_id, 'text_message', {
            'length': len(message.text),
            'has_question': '?' in message.text,
            'time': datetime.now().hour
        })
        
        # Personalized response based on user patterns
        user_patterns = advanced_dna.learning_data.get("user_patterns", {}).get(str(user_id), {})
        
        response = f"📝 *אתה כתבת:*\n`{message.text[:200]}`\n\n"
        
        # Add contextual response based on patterns
        if user_patterns.get("command_frequency", {}).get("quiz", 0) > 2:
            response += f"💡 *טיפ:* נסה `/quiz` למשחק חדש!\n\n"
        
        if user_patterns.get("command_frequency", {}).get("stock", 0) > 1:
            response += f"💹 *טיפ:* בדוק מניה עם `/stock AAPL`\n\n"
        
        response += f"🤖 *ID הבוט:* `{BOT_ID}`\n"
        response += f"📊 *הודעה #{bot_stats.stats['message_count']} שלך*"
        
        update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

# ==================== ADMIN COMMANDS ENHANCEMENT ====================
def admin_panel(update, context):
    """Enhanced admin panel"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode=ParseMode.MARKDOWN)
        return
    
    log_message(update, 'admin')
    
    stats = bot_stats.get_summary()
    dna_report = advanced_dna.get_evolution_report()
    
    admin_text = (
        f"👑 *לוח בקרה למנהל מתקדם - {BOT_NAME}*\n\n"
        f"*מנהל:* {user.first_name} (ID: `{user.id}`)\n"
        f"*בוט:* {BOT_NAME} (ID: `{BOT_ID}`)\n"
        f"*דור אבולוציה:* {dna_report['dna_info']['generation']}\n"
        f"*דירוג התאמה:* {dna_report['dna_info']['fitness_score']}/100\n\n"
        
        f"📊 *סטטיסטיקות מהירות:*\n"
        f"• 📨 הודעות: {stats['total_messages']}\n"
        f"• 👥 משתמשים: {stats['total_users']}\n"
        f"• 👥 פעילים: {stats['active_users']}\n"
        f"• 👥 קבוצות: {len(bot_stats.stats['groups'])}\n"
        f"• 🚀 התחלות: {stats['start_count']}\n"
        f"• 📢 שידורים: {len(broadcasts_db)}\n"
        f"• ❌ שגיאות: {stats['errors_count']}\n\n"
        
        f"⚙️ *פעולות מנהל מתקדמות:*\n"
        "השתמש בתפריט למטה או בפקודות:\n"
        "/stats - סטטיסטיקות מפורטות\n"
        "/broadcast - שידור לכולם\n"
        "/users - ניהול משתמשים\n"
        "/system_check - בדיקת מערכת\n"
        "/dna_report - דוח DNA\n"
        "/evolution_status - סטטוס אבולוציה\n"
        "/restart - אתחול בוט"
    )
    
    update.message.reply_text(
        admin_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

# ==================== SETUP HANDLERS ====================
# Command handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("menu", menu_command))
dispatcher.add_handler(CommandHandler("features", features_command))
dispatcher.add_handler(CommandHandler("profile", profile_command))
dispatcher.add_handler(CommandHandler("id", show_id))
dispatcher.add_handler(CommandHandler("info", bot_info))
dispatcher.add_handler(CommandHandler("ping", ping))

# New feature commands
dispatcher.add_handler(CommandHandler("stock", stock_command))
dispatcher.add_handler(CommandHandler("analyze", analyze_command))
dispatcher.add_handler(CommandHandler("exchange", exchange_command))
dispatcher.add_handler(CommandHandler("quiz", quiz_command))
dispatcher.add_handler(CommandHandler("trivia", trivia_command))
dispatcher.add_handler(CommandHandler("leaderboard", leaderboard_command))
dispatcher.add_handler(CommandHandler("answer", answer_command))
dispatcher.add_handler(CommandHandler("task", task_command))

# DNA evolution commands
dispatcher.add_handler(CommandHandler("dna", dna_command))
dispatcher.add_handler(CommandHandler("evolve", evolve_command, pass_args=True))
dispatcher.add_handler(CommandHandler("lineage", lineage_command))

# Admin commands
dispatcher.add_handler(CommandHandler("admin", admin_panel))
dispatcher.add_handler(CommandHandler("stats", admin_stats))
dispatcher.add_handler(CommandHandler("broadcast", broadcast_command, pass_args=True))
dispatcher.add_handler(CommandHandler("users", users_command))
dispatcher.add_handler(CommandHandler("export", export_command))
dispatcher.add_handler(CommandHandler("restart", restart_command))

# Callback query handler (for inline buttons)
dispatcher.add_handler(CallbackQueryHandler(button_callback))

# Text message handler (for buttons and group mentions)
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

# Unknown command handler (must be last)
dispatcher.add_handler(MessageHandler(Filters.command, unknown))

# Add error handler
dispatcher.add_error_handler(error_handler)

# ==================== ENHANCED FLASK ROUTES ====================
@app.route('/')
def home():
    """Enhanced home page"""
    stats = bot_stats.get_summary()
    dna_report = advanced_dna.get_evolution_report()
    
    return jsonify({
        "status": "online",
        "service": "evolutionary-telegram-bot",
        "bot": {
            "name": BOT_NAME,
            "username": BOT_USERNAME,
            "id": BOT_ID,
            "link": f"t.me/{BOT_USERNAME}" if BOT_USERNAME else None,
            "generation": dna_report['dna_info']['generation'],
            "fitness_score": dna_report['dna_info']['fitness_score']
        },
        "stats": {
            "uptime": stats['uptime'],
            "messages": stats['total_messages'],
            "unique_users": stats['total_users'],
            "active_users": stats['active_users'],
            "active_groups": len(bot_stats.stats['groups']),
            "starts": stats['start_count'],
            "commands": stats['commands_count']
        },
        "storage": {
            "users": len(users_db),
            "messages": len(messages_db),
            "broadcasts": len(broadcasts_db),
            "groups": len(groups_db),
            "stocks": len(stocks_db),
            "tasks": len(tasks_db),
            "quiz_scores": len(quiz_scores_db)
        },
        "dna": {
            "generation": dna_report['dna_info']['generation'],
            "modules": dna_report['dna_info']['total_modules'],
            "mutations": dna_report['dna_info']['total_mutations'],
            "fitness": dna_report['dna_info']['fitness_score'],
            "adaptation_level": dna_report['dna_info']['adaptation_level']
        },
        "features": {
            "financial": bool(ALPHAVANTAGE_API_KEY),
            "quiz_games": True,
            "task_management": True,
            "dna_evolution": True,
            "learning_system": True,
            "admin_tools": True,
            "broadcast": True,
            "group_management": True
        },
        "api_endpoints": {
            "health": "/health",
            "bot_info": "/bot/info",
            "system_status": "/system/status",
            "evolution_report": "/evolution/report"
        }
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint with enhanced security"""
    # Check webhook secret if set
    if WEBHOOK_SECRET and WEBHOOK_SECRET.strip():
        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret != WEBHOOK_SECRET:
            logger.warning(f"Unauthorized webhook attempt. Expected: '{WEBHOOK_SECRET}', Got: '{secret}'")
            return 'Unauthorized', 403
    else:
        logger.warning("WEBHOOK_SECRET not set, webhook is unsecured!")
    
    try:
        data = request.get_json()
        
        # Log webhook request
        if 'message' in data and 'text' in data['message']:
            msg = data['message']
            logger.info(f"📨 Webhook: {msg['from'].get('first_name', 'Unknown')}: "
                       f"{msg['text'][:50]}...")
        
        update = Update.de_json(data, bot)
        dispatcher.process_update(update)
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        bot_stats.update('error')
        return 'Error', 500

@app.route('/health')
def health():
    """Enhanced health check endpoint"""
    try:
        # Test bot connection
        bot_info = bot.get_me()
        
        # Check storage
        storage_ok = all([
            os.path.exists(USERS_FILE),
            os.path.exists(DATA_DIR)
        ])
        
        # Check API connections
        api_status = "ok"
        if ALPHAVANTAGE_API_KEY:
            try:
                # Quick test of Alpha Vantage
                test_response = requests.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "GLOBAL_QUOTE", "symbol": "AAPL", "apikey": ALPHAVANTAGE_API_KEY},
                    timeout=5
                )
                if test_response.status_code != 200:
                    api_status = "alpha_vantage_error"
            except:
                api_status = "alpha_vantage_timeout"
        
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "bot": {
                "name": bot_info.first_name,
                "id": bot_info.id,
                "username": bot_info.username,
                "running": True
            },
            "system": {
                "storage": storage_ok,
                "api_connections": api_status,
                "memory_usage": len(users_db) + len(messages_db),
                "active_games": len(quiz_system.active_games),
                "scheduled_tasks": len([t for t in tasks_db if not t.get('completed')])
            },
            "stats": {
                "messages": bot_stats.stats['message_count'],
                "users": len(bot_stats.stats['users']),
                "active_users": len(bot_stats.stats['active_users']),
                "groups": len(bot_stats.stats['groups']),
                "uptime": bot_stats.stats['start_time']
            },
            "dna": {
                "generation": advanced_dna.dna.get("generation", 1),
                "fitness": advanced_dna.dna.get("fitness_score", 0),
                "adaptation_level": advanced_dna.dna.get("adaptation_level", 0),
                "modules_active": len([m for m in advanced_dna.dna.get("modules", {}).values() 
                                     if m.get("status") == "active"])
            }
        }
        
        return jsonify(health_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/system/status')
def system_status():
    """System status endpoint"""
    stats = bot_stats.get_summary()
    dna_report = advanced_dna.get_evolution_report()
    
    # Calculate system metrics
    active_tasks = len([t for t in tasks_db if not t.get('completed')])
    active_games = len(quiz_system.active_games)
    
    # Memory usage estimation
    memory_estimation = {
        "users": len(users_db) * 500,  # ~500 bytes per user
        "messages": len(messages_db) * 200,  # ~200 bytes per message
        "tasks": len(tasks_db) * 300,  # ~300 bytes per task
        "dna": len(str(advanced_dna.dna))  # DNA size
    }
    total_memory_est = sum(memory_estimation.values())
    
    status = {
        "system": {
            "uptime": stats['uptime'],
            "message_rate": f"{stats['total_messages'] / max(1, bot_stats.stats['uptime_seconds'] / 3600):.1f}/hour",
            "active_components": {
                "tasks": active_tasks,
                "games": active_games,
                "scheduled_reminders": len([t for t in tasks_db if t.get('reminder_time')])
            },
            "memory_estimation_bytes": total_memory_est,
            "error_rate": f"{(stats['errors_count'] / max(1, stats['total_messages'])) * 100:.2f}%"
        },
        "evolution": {
            "current_generation": dna_report['dna_info']['generation'],
            "fitness_score": dna_report['dna_info']['fitness_score'],
            "progress": dna_report['progress']['percent'],
            "level": dna_report['progress']['level'],
            "total_mutations": dna_report['dna_info']['total_mutations'],
            "active_modules": len([m for m in dna_report.get('active_modules', [])])
        },
        "features": {
            "financial": {
                "enabled": bool(ALPHAVANTAGE_API_KEY),
                "requests_today": 0  # Could track this
            },
            "quiz": {
                "total_games": sum(len(scores) for scores in quiz_scores_db.values()),
                "active_games": active_games,
                "leaderboard_entries": len(quiz_system.get_leaderboard())
            },
            "tasks": {
                "total": len(tasks_db),
                "completed": len([t for t in tasks_db if t.get('completed')]),
                "pending": active_tasks
            }
        },
        "storage_summary": {
            "users": len(users_db),
            "messages": len(messages_db),
            "groups": len(groups_db),
            "broadcasts": len(broadcasts_db),
            "quiz_scores": sum(len(scores) for scores in quiz_scores_db.values())
        }
    }
    
    return jsonify(status)

@app.route('/evolution/report')
def evolution_report():
    """Evolution system report"""
    report = advanced_dna.get_evolution_report()
    
    # Add learning insights
    learning_data = advanced_dna.learning_data
    
    enhanced_report = {
        "dna": report,
        "learning": {
            "total_user_patterns": len(learning_data.get("user_patterns", {})),
            "total_command_patterns": len(learning_data.get("command_patterns", {})),
            "user_engagement": {
                "total_users": len(users_db),
                "active_users": len(bot_stats.stats['active_users']),
                "engagement_rate": f"{(len(bot_stats.stats['active_users']) / max(1, len(users_db))) * 100:.1f}%"
            }
        },
        "system_performance": {
            "message_throughput": f"{bot_stats.stats['message_count'] / max(1, bot_stats.stats['uptime_seconds'] / 3600):.1f}/hour",
            "command_distribution": dict(sorted(
                bot_stats.stats['commands_count'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
            "peak_hours": sorted(
                bot_stats.get_hourly_activity(),
                key=lambda x: x['count'],
                reverse=True
            )[:3]
        }
    }
    
    return jsonify(enhanced_report)

# ==================== ENHANCED INITIALIZATION ====================
def setup_webhook():
    """Enhanced webhook setup with secret token"""
    if WEBHOOK_URL:
        try:
            # Ensure webhook URL ends with /webhook
            webhook_url = WEBHOOK_URL.rstrip('/') + '/webhook'
            
            # Set webhook with secret token
            bot.set_webhook(
                url=webhook_url,
                secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET and WEBHOOK_SECRET.strip() else None
            )
            
            logger.info(f"✅ Webhook configured: {webhook_url}")
            logger.info(f"🔐 Webhook secret: {'Enabled' if WEBHOOK_SECRET else 'Disabled'}")
            logger.info(f"🤖 Bot ID: {BOT_ID}, Username: @{BOT_USERNAME}")
            
        except Exception as e:
            logger.error(f"⚠️ Webhook setup failed: {e}")
            logger.warning("Bot will still run but webhook won't work properly")
    else:
        logger.warning("⚠️ WEBHOOK_URL not set, webhook not configured")

if __name__ == '__main__':
    logger.info("🚀 Starting Enhanced Evolutionary Telegram Bot")
    
    # Initialize enhanced evolution system
    initialize_evolution()
    
    # Setup webhook
    setup_webhook()
    
    # Log startup info with enhanced details
    stats = bot_stats.get_summary()
    dna_report = advanced_dna.get_evolution_report()
    
    logger.info(f"🧬 Bot DNA: Generation {dna_report['dna_info']['generation']}, "
                f"Modules: {dna_report['dna_info']['total_modules']}, "
                f"Mutations: {dna_report['dna_info']['total_mutations']}, "
                f"Fitness: {dna_report['dna_info']['fitness_score']}")
    
    logger.info(f"🤖 Bot: {BOT_NAME} (@{BOT_USERNAME}, ID: {BOT_ID})")
    logger.info(f"👑 Admin ID: {ADMIN_USER_ID or 'Not configured'}")
    logger.info(f"💰 Financial API: {'Enabled' if ALPHAVANTAGE_API_KEY else 'Disabled'}")
    logger.info(f"🔐 Webhook Secret: {'Set' if WEBHOOK_SECRET and WEBHOOK_SECRET.strip() else 'Not set'}")
    
    logger.info(f"💾 Storage: {len(users_db)} users, {len(groups_db)} groups, "
                f"{len(messages_db)} messages, {len(tasks_db)} tasks")
    
    logger.info(f"📊 Initial Stats: {stats['total_messages']} messages, "
                f"{stats['total_users']} users, {stats['active_users']} active")
    
    logger.info(f"🌐 Flask starting on port {PORT}")
    logger.info(f"⚙️ Workers: {dispatcher.workers}")
    
    # Start auto-evolution check in background
    auto_evolve_thread = threading.Thread(target=auto_evolve_check, daemon=True)
    auto_evolve_thread.start()
    
    # Start Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
