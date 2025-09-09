from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import math
from datetime import datetime

# Простое хранилище
players_db = {}
rooms_db = {}
room_counter = 1

# Данные турниров
tournaments_db = {}
tournament_games = {}
tournament_counter = 0
current_tournament = None

# Система рейтинга Glicko-2 для бадминтона
class Glicko2Rating:
    def __init__(self, rating=1500, rd=350, vol=0.06):
        self.rating = rating
        self.rd = rd  # Rating Deviation
        self.vol = vol  # Volatility
    
    def calculate_g(self, rd):
        """Вычисляет g(RD)"""
        return 1 / math.sqrt(1 + (3 * (rd ** 2)) / (math.pi ** 2))
    
    def calculate_e(self, opponent_rating, opponent_rd):
        """Вычисляет E(s|r, rj, RDj)"""
        g = self.calculate_g(opponent_rd)
        return 1 / (1 + math.exp(-g * (self.rating - opponent_rating) / 400))
    
    def update_rating(self, results, tau=0.5):
        """Обновляет рейтинг на основе результатов игр
        results: список кортежей (opponent_rating, opponent_rd, score)
        score: 1 за победу, 0 за поражение, 0.5 за ничью
        """
        if not results:
            return self.rating, self.rd, self.vol
        
        # Шаг 1: Вычисляем v (variance)
        v = 0
        for opp_rating, opp_rd, score in results:
            g = self.calculate_g(opp_rd)
            e = self.calculate_e(opp_rating, opp_rd)
            v += (g ** 2) * e * (1 - e)
        
        if v == 0:
            return self.rating, self.rd, self.vol
        
        v = 1 / v
        
        # Шаг 2: Вычисляем delta
        delta = 0
        for opp_rating, opp_rd, score in results:
            g = self.calculate_g(opp_rd)
            e = self.calculate_e(opp_rating, opp_rd)
            delta += g * (score - e)
        
        delta *= v
        
        # Шаг 3: Обновляем volatility
        a = math.log(self.vol ** 2)
        
        def f(x):
            ex = math.exp(x)
            return (ex * (delta ** 2 - self.rd ** 2 - v - ex) / 
                   (2 * (self.rd ** 2 + v + ex) ** 2)) - (x - a) / (tau ** 2)
        
        # Простое приближение для нахождения корня
        A = a
        if delta ** 2 > self.rd ** 2 + v:
            B = math.log(delta ** 2 - self.rd ** 2 - v)
        else:
            k = 1
            while f(a - k * tau) < 0:
                k += 1
            B = a - k * tau
        
        fA = f(A)
        fB = f(B)
        
        while abs(B - A) > 0.000001:
            C = A + (A - B) * fA / (fB - fA)
            fC = f(C)
            if fC * fB < 0:
                A = B
                fA = fB
            else:
                fA = fA / 2
            B = C
            fB = fC
        
        new_vol = math.exp(A / 2)
        
        # Шаг 4: Обновляем RD
        new_rd = math.sqrt(self.rd ** 2 + new_vol ** 2)
        
        # Шаг 5: Обновляем рейтинг
        new_rating = self.rating + (new_rd ** 2) * delta
        
        return int(new_rating), int(new_rd), new_vol

def calculate_team_rating(players, is_winner):
    """Вычисляет командный рейтинг для 2v2"""
    if len(players) != 2:
        return 1500
    
    # Средний рейтинг команды
    avg_rating = sum(p['rating'] for p in players) / 2
    
    # Бонус за командную игру (5% от среднего рейтинга)
    team_bonus = avg_rating * 0.05
    
    return int(avg_rating + team_bonus)

def calculate_rating_changes(room_data, score_data):
    """Вычисляет изменения рейтинга после игры
    score_data: {'team1': [player_ids], 'team2': [player_ids], 'score1': int, 'score2': int}
    """
    team1_players = [players_db[pid] for pid in score_data['team1'] if pid in players_db]
    team2_players = [players_db[pid] for pid in score_data['team2'] if pid in players_db]
    
    score1 = score_data['score1']
    score2 = score_data['score2']
    
    # Определяем победителя
    if score1 > score2:
        team1_won = True
        team2_won = False
    elif score2 > score1:
        team1_won = False
        team2_won = True
    else:
        # Ничья
        team1_won = False
        team2_won = False
    
    changes = {}
    
    # Обрабатываем команду 1
    if team1_players:
        team1_rating = calculate_team_rating(team1_players, team1_won)
        
        for player in team1_players:
            glicko = Glicko2Rating(player['rating'], 350, 0.06)
            
            # Создаем результаты против команды 2
            results = []
            if team2_players:
                team2_rating = calculate_team_rating(team2_players, team2_won)
                score = 1 if team1_won else (0.5 if not team1_won and not team2_won else 0)
                results.append((team2_rating, 350, score))
            
            new_rating, new_rd, new_vol = glicko.update_rating(results)
            old_rating = player['rating']
            rating_change = new_rating - old_rating
            
            changes[player['telegram_id']] = {
                'old_rating': old_rating,
                'new_rating': new_rating,
                'rating_change': rating_change,
                'team': 1,
                'won': team1_won
            }
            
            # Обновляем рейтинг в базе
            player['rating'] = new_rating
    
    # Обрабатываем команду 2
    if team2_players:
        team2_rating = calculate_team_rating(team2_players, team2_won)
        
        for player in team2_players:
            glicko = Glicko2Rating(player['rating'], 350, 0.06)
            
            # Создаем результаты против команды 1
            results = []
            if team1_players:
                team1_rating = calculate_team_rating(team1_players, team1_won)
                score = 1 if team2_won else (0.5 if not team1_won and not team2_won else 0)
                results.append((team1_rating, 350, score))
            
            new_rating, new_rd, new_vol = glicko.update_rating(results)
            old_rating = player['rating']
            rating_change = new_rating - old_rating
            
            changes[player['telegram_id']] = {
                'old_rating': old_rating,
                'new_rating': new_rating,
                'rating_change': rating_change,
                'team': 2,
                'won': team2_won
            }
            
            # Обновляем рейтинг в базе
            player['rating'] = new_rating
    
    return changes

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Обработка GET запросов"""
        path = self.path.split('?')[0]
        
        # CORS заголовки
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        try:
            if path == '/':
                response = {
                    "message": "🏸 Badminton Rating API",
                    "version": "1.0.0",
                    "status": "active",
                    "database": "memory",
                    "players": len(players_db),
                    "rooms": len(rooms_db)
                }
                
            elif path == '/health':
                response = {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat()
                }
                
            elif path == '/rooms/':
                # Возвращаем все комнаты
                active_rooms = [room for room in rooms_db.values() if room.get("is_active", True)]
                response = active_rooms
                
            elif path.startswith('/rooms/') and path != '/rooms/':
                # Получение конкретной комнаты
                room_id = int(path.split('/')[-1])
                if room_id in rooms_db:
                    response = rooms_db[room_id]
                else:
                    self.send_response(404)
                    response = {"error": "Комната не найдена"}
                    
            elif path.startswith('/players/'):
                # Получение игрока
                telegram_id = int(path.split('/')[-1])
                if telegram_id in players_db:
                    response = players_db[telegram_id]
                else:
                    response = {
                        "id": telegram_id,
                        "telegram_id": telegram_id,
                        "first_name": "Неизвестный",
                        "last_name": "Игрок",
                        "username": None,
                        "rating": 1500
                    }
            else:
                self.send_response(404)
                response = {"error": "Endpoint not found"}
                
        except Exception as e:
            self.send_response(500)
            response = {"error": str(e)}
        
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
    
    def do_POST(self):
        """Обработка POST запросов"""
        global room_counter
        
        # CORS заголовки
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        try:
            content_length_str = self.headers.get('Content-Length')
            content_length = int(content_length_str) if content_length_str else 0
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
            else:
                data = {}
            
            path = self.path.split('?')[0]
            print(f"🔍 POST запрос: {path}, data: {data}")
            
            if path == '/players/':
                # Создание/обновление игрока
                if 'telegram_id' not in data:
                    self.send_response(400)
                    response = {"error": "telegram_id required"}
                else:
                    telegram_id = data['telegram_id']
                    player = {
                        "id": telegram_id,
                        "telegram_id": telegram_id,
                        "first_name": data['first_name'],
                        "last_name": data.get('last_name'),
                        "username": data.get('username'),
                        "rating": 1500
                    }
                    players_db[telegram_id] = player
                    response = player
                
            elif path == '/rooms/':
                # Создание комнаты
                if 'creator_telegram_id' not in data:
                    self.send_response(400)
                    response = {"error": "creator_telegram_id required"}
                else:
                    creator_id = data['creator_telegram_id']
                    
                    # ПРОВЕРЯЕМ НЕ СОЗДАЛ ЛИ УЖЕ КОМНАТУ
                    existing_room = None
                    for room_id, room in rooms_db.items():
                        if room['creator_id'] == creator_id:
                            existing_room = room_id
                            break
                    
                    if existing_room:
                        self.send_response(400)
                        response = {"error": f"Вы уже создали комнату #{existing_room}. Можно создать только одну комнату."}
                    else:
                        # Создаем игрока если его нет
                        if creator_id not in players_db:
                            players_db[creator_id] = {
                                "id": creator_id,
                                "telegram_id": creator_id,
                                "first_name": "Игрок",
                                "last_name": f"{creator_id}",
                                "username": None,
                                "rating": 1500
                            }
                    
                        creator = players_db[creator_id]
                        creator_full_name = f"{creator['first_name']} {creator.get('last_name', '')}".strip()
                        
                        # Создаем комнату
                        new_room = {
                            "id": room_counter,
                            "name": data['name'],
                            "creator_id": creator_id,
                            "creator_full_name": creator_full_name,
                            "max_players": data.get('max_players', 4),
                            "member_count": 1,
                            "is_active": True,
                            "created_at": datetime.now().isoformat(),
                            "members": [
                                {
                                    "id": 1,
                                    "player": creator,
                                    "is_leader": True,
                                    "joined_at": datetime.now().isoformat()
                                }
                            ]
                        }
                        
                        rooms_db[room_counter] = new_room
                        room_counter += 1
                        response = new_room
                
            elif path.startswith('/rooms/') and path.endswith('/join'):
                # Присоединение к комнате
                room_id = int(path.split('/')[-2])
                telegram_id = data['telegram_id']
                first_name = data.get('first_name', 'Игрок')
                last_name = data.get('last_name', '')
                username = data.get('username')
                
                if room_id not in rooms_db:
                    self.send_response(404)
                    response = {"error": "Комната не найдена"}
                else:
                    room = rooms_db[room_id]
                    
                    # Проверяем не присоединился ли уже
                    already_joined = any(member['player']['telegram_id'] == telegram_id for member in room['members'])
                    
                    if already_joined:
                        response = {"message": "Вы уже в комнате", "room": room}
                    elif len(room['members']) >= room['max_players']:
                        self.send_response(400)
                        response = {"error": "Комната заполнена"}
                    else:
                        # Создаем/обновляем игрока
                        if telegram_id not in players_db:
                            players_db[telegram_id] = {
                                "id": telegram_id,
                                "telegram_id": telegram_id,
                                "first_name": first_name,
                                "last_name": last_name,
                                "username": username,
                                "rating": 1500
                            }
                        else:
                            # Обновляем данные игрока
                            players_db[telegram_id].update({
                                "first_name": first_name,
                                "last_name": last_name,
                                "username": username
                            })
                        
                        player = players_db[telegram_id]
                        
                        # Добавляем игрока в комнату
                        new_member = {
                            "id": len(room['members']) + 1,
                            "player": player,
                            "is_leader": False,
                            "joined_at": datetime.now().isoformat()
                        }
                        
                        room['members'].append(new_member)
                        room['member_count'] = len(room['members'])
                        
                        # Обновляем комнату в базе
                        rooms_db[room_id] = room
                        
                        response = {
                            "message": "Успешно присоединились к комнате",
                            "room": room,
                            "member": new_member
                        }
                        
            elif path.startswith('/rooms/') and path.endswith('/leave'):
                # Выход из комнаты
                room_id = int(path.split('/')[-2])
                telegram_id = data['telegram_id']
                
                if room_id not in rooms_db:
                    self.send_response(404)
                    response = {"error": "Комната не найдена"}
                else:
                    room = rooms_db[room_id]
                    
                    # Находим участника для удаления
                    member_to_remove = None
                    for i, member in enumerate(room['members']):
                        if member['player']['telegram_id'] == telegram_id:
                            member_to_remove = i
                            break
                    
                    if member_to_remove is not None:
                        # Удаляем участника
                        removed_member = room['members'].pop(member_to_remove)
                        room['member_count'] = len(room['members'])
                        
                        # ЕСЛИ СОЗДАТЕЛЬ ПОКИДАЕТ КОМНАТУ - РАСФОРМИРОВЫВАЕМ ПОЛНОСТЬЮ
                        if room['creator_id'] == telegram_id:
                            # Создаем список участников для уведомления
                            remaining_members = [member['player']['telegram_id'] for member in room['members']]
                            
                            # Удаляем комнату полностью
                            del rooms_db[room_id]
                            
                            response = {
                                "message": "Комната расформирована",
                                "room_disbanded": True,
                                "affected_members": remaining_members
                            }
                        elif len(room['members']) == 0:
                            # Если комната пуста - удаляем её
                            del rooms_db[room_id]
                            response = {"message": "Вы покинули комнату. Комната удалена."}
                        else:
                            # Обычный выход участника
                            rooms_db[room_id] = room
                            response = {
                                "message": "Вы покинули комнату",
                                "room": room,
                                "removed_member": removed_member
                            }
                    else:
                        self.send_response(400)
                        response = {"error": "Вы не состоите в этой комнате"}
                
            else:
                self.send_response(404)
                response = {"error": "Endpoint not found"}
                
        except Exception as e:
            self.send_response(500)
            response = {"error": str(e)}
        
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
    
    def do_DELETE(self):
        """Обработка DELETE запросов"""
        # CORS заголовки
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        try:
            path = self.path.split('?')[0]
            
            if path.startswith('/rooms/') and path != '/rooms/':
                room_id = int(path.split('/')[-1])
                if room_id in rooms_db:
                    del rooms_db[room_id]
                    response = {"message": "Комната успешно удалена"}
                else:
                    self.send_response(404)
                    response = {"error": "Комната не найдена"}
                    
            elif path.startswith('/rooms/') and path.endswith('/finish-game'):
                # Завершение игры и подсчет рейтинга
                room_id = int(path.split('/')[-2])
                
                if room_id not in rooms_db:
                    self.send_response(404)
                    response = {"error": "Комната не найдена"}
                else:
                    room = rooms_db[room_id]
                    
                    # Проверяем что в комнате 2 или 4 игрока
                    if len(room['members']) not in [2, 4]:
                        self.send_response(400)
                        response = {"error": "Для завершения игры нужно 2 или 4 игрока"}
                    else:
                        # Получаем данные счета
                        score_data = data
                        
                        # Вычисляем изменения рейтинга
                        rating_changes = calculate_rating_changes(room, score_data)
                        
                        # Обновляем комнату - игра завершена
                        room['game_finished'] = True
                        room['final_score'] = {
                            'team1': score_data['score1'],
                            'team2': score_data['score2']
                        }
                        room['rating_changes'] = rating_changes
                        room['finished_at'] = datetime.now().isoformat()
                        
                        # Записываем игру в турнир, если он активен
                        if current_tournament is not None:
                            game_data = {
                                "tournament_id": current_tournament,
                                "room_id": room_id,
                                "timestamp": datetime.now().isoformat(),
                                "team1": score_data['team1'],
                                "team2": score_data['team2'],
                                "score1": score_data['score1'],
                                "score2": score_data['score2'],
                                "rating_changes": rating_changes
                            }
                            tournament_games[current_tournament].append(game_data)
                        
                        response = {
                            "message": "Игра завершена!",
                            "room": room,
                            "rating_changes": rating_changes
                        }
                        
            elif path == '/tournament/start':
                # Начать турнир
                response = self.start_tournament()
            elif path == '/tournament/end':
                # Завершить турнир
                response = self.end_tournament()
            elif path.startswith('/tournament/'):
                # Получение данных турнира
                tournament_id = int(path.split('/')[-1])
                response = self.get_tournament_data(tournament_id)
                        
            else:
                self.send_response(404)
                response = {"error": "Endpoint not found"}
                
        except Exception as e:
            self.send_response(500)
            response = {"error": str(e)}
        
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
    
    def start_tournament(self):
        """Начать турнир"""
        global tournament_counter, current_tournament
        
        tournament_counter += 1
        current_tournament = tournament_counter
        
        tournaments_db[current_tournament] = {
            "id": current_tournament,
            "start_time": datetime.now().isoformat(),
            "status": "active"
        }
        
        tournament_games[current_tournament] = []
        
        return {
            "message": f"Турнир #{current_tournament} начат!",
            "tournament_id": current_tournament
        }
    
    def end_tournament(self):
        """Завершить турнир"""
        global current_tournament
        
        if current_tournament is None:
            return {"error": "Нет активного турнира"}
        
        tournament_id = current_tournament
        tournaments_db[tournament_id]["status"] = "finished"
        tournaments_db[tournament_id]["end_time"] = datetime.now().isoformat()
        
        current_tournament = None
        
        return {
            "message": f"Турнир #{tournament_id} завершен!",
            "tournament_id": tournament_id
        }
    
    def get_tournament_data(self, tournament_id):
        """Получить данные турнира"""
        if tournament_id not in tournaments_db:
            return {"error": "Турнир не найден"}
        
        tournament = tournaments_db[tournament_id]
        games = tournament_games.get(tournament_id, [])
        
        return {
            "tournament_id": tournament_id,
            "tournament": tournament,
            "games": games,
            "message": f"Данные турнира #{tournament_id}"
        }
    
    def do_OPTIONS(self):
        """Обработка OPTIONS запросов для CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

if __name__ == '__main__':
    from http.server import HTTPServer
    server = HTTPServer(('localhost', 8000), handler)
    print('🚀 API сервер запущен на http://localhost:8000')
    server.serve_forever()