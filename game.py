
"""
- 两个AI程序各自控制N个agent在一个网格的地图中进行比拼
- 比赛分为攻守两方，防守方需要在控制多个agent不断探索地图，并获得分数奖励的同时，尽可能躲避攻击方的追击；攻击方需要控制多个agent尽可能的追击并抓获防守方，以此获得分数奖励；
- 攻击方无法直接从地图获得奖励，每次捕获到对方后，可以获得被捕获的agent身上奖励的一半作为奖励；被捕获的agent会回到出生位置；回到出生位置的防守方agent会获得一个无法被攻击的buff，持续3回合；
- 视野：AGV有着以自己为中心7*7格子的视野范围，己方看不到视野范围外的地图情况
- 地图上存在多种道具，获得道具的agent能够获得相应的能力，有助于取得优势，道具包括：
    - 隐身道具，获得隐身道具的agent可以获得隐身能力，无法被对手看到，持续12回合，只有防守方可以获得隐身道具
    - 穿墙道具，获得穿墙道具的agent可以获得无视障碍物移动的能力，持续12回合
    - 视野增加道具，获得道具的agent视野范围会扩大5格,持续12回合
    - 防守道具，获得防守道具的agent可以获得免疫攻击的能力，持续12回合，只有防守方可以获得防守道具
    - 攻击道具，获得攻击道具的agent可以获得无视对手的防御道具，并且能够获得对方所有的金币，持续12回合，只有攻击方可以获得防守道具
    - 金币，吃到金币可以获得分数奖励，只有防守方可以获得金币
    - 所有道具会在地图的固定区域内生成，但是每个网格上具体生成哪些道具由随机数控制
    - agent移动到道具所在网格，则认为吃了道具，道具立即生效
    - agent移动到金币所在网格，则认为吃了金币
- 除了道具之外，地图中还存在其他元素，包括：
    - 墙体：agent无法移动到墙体上面，也无法穿越墙体
    - 传送门：地图上存在成对出现的传送门，从传送门一端进入会立即从另一端出来
- 碰撞规则，以下情形会发生碰撞：
    - 攻击方或者防守方内部的agent之间没有碰撞关系
    - 所有agent和墙体会发生碰撞，持有穿墙道具的agent除外
    - agent无法移动出地图边界，如果尝试会留在原地
    - 攻击方和防守方之间存在碰撞，当攻击方的agent和防守方的agent发生碰撞的时候认为攻击方成功捕捉到防守方，防守方会立即回到出生地，攻击方会移动到目的地
- 每个回合，比赛服务器会告知AI程序所有它所控制的agent的状态，包括每个agent的状态包括金币持有数量、持有什么道具，道具持续时间等，以及每个agent视野范围内的所有墙体，传送门 ，道具，以及agent信息；AI程序根据以上信息进行计算，输出每个agent的动作，动作只能为：UP、DOWN、LEFT、RIGHT、STAY,分别表示朝上下左右移动一格和原地停留，服务器不接受其他动作，所有非法动作会造成agent留在原地
- 每局比赛分两轮进行，第一轮结束后会交换双方角色再进行一次轮比赛，以保证公平性，比赛成绩取两轮获得的总分数
- 每轮比赛结束的条件为：
    - 地图上所有金币被吃掉
    - 到达最大回合数上限
"""


from enum import Enum, auto
from typing import List, Dict, Tuple
from collections import defaultdict

import json
import random

import logging

logger = logging.getLogger('game')

class CellType(Enum):
    WALL = auto()
    PORTAL = auto()
    COIN = auto()
    POWERUP = auto()
    ATTACKER = auto()
    DEFENDER = auto()

class Powerup(Enum):
    INVISIBILITY = auto()
    PASSWALL = auto()
    EXTRAVISION = auto()
    SHIELD = auto()
    SWORD = auto()


class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    STAY = "STAY"


class Agent:
    ATTACKER = "ATTACKER"
    DEFENDER = "DEFENDER"

    def __init__(self, id: int, pos: Tuple[int, int], role: str,player_id: str,vision_range: int):
        self.id = id
        self.pos = pos
        self.next_pos = pos
        self.powerups = {}  # 当前持有的道具
        self.role = role  # ATTACKER 或 DEFENDER
        self.player_id = player_id
        self.vision_range = vision_range
        self.score = 0
        self.invulnerability_duration = 0
        self.origin_pos = pos


    def __str__(self):
        return str(self.__dict__)

    __repr__ = __str__
    

def chain_agents(agents1,agents2):
    for a in agents1:
        yield a
    for b in agents2:
        yield b

class Game:
    def __init__(self, map: Dict):
        # map的内容格式如下:
        # {
        #   "map_conf": {
        #     "height": 12,
        #     "width": 15,
        #     ”coin_score“: 10,
        #     "invulnerability_duration": 3,
        #     "max_steps": 1152,
        #     "vision_range": 3
        #   },
        #   "powerup_conf": {
        #     "invisibility": {
        #         "duration": 5
        #     },
        #     "passwall": {
        #         "duration": 5
        #     },
        #     "extravision": {
        #         "duration": 5,
        #         "extra": 5,
        #     }
        #     "shield": {
        #         "duration": 5
        #     }
        #   },
        #   "map": [
        #     {"x":0,"y":0,"type": "WALL"},
        #     {"x":0,"y":1,"type": "COIN"},
        #     {"x":0,"y":2,"type": "POWERUP"},
        #     {"x":0,"y":3,"type": "PORTAL", "pair": {"x":1,"y":0},"name": "A"},
        #     {"x":0,"y":3,"type": "ATTACKER"},
        #     {"x":0,"y":3,"type": "DEFENDER"},
        #   ]
        # }
        self.map_template = self._load_map(map['map'])
        self.map_conf = map['map_conf']
        self.powerup_conf = map['powerup_conf']
        self.map: Dict[Tuple[int,int],Dict] = {} #地图状态信息
        self.agents: Dict[str, Agent] = {}
        self.steps = 0
        self.rand = None
        self.attacker_time_used = 0
        self.defender_time_used = 0
        self.attacker = None
        self.defender = None
        self.logs = []


    def _load_map(self, map_data: Dict) -> Tuple[Dict[Tuple[int, int], str],Dict,Dict]:
        map_template = {}
        for cell in map_data:
            x = cell['x']
            y = cell['y']
            cell_type = cell['type']
            o = {"type": CellType[cell_type]}
            
            if cell_type == 'PORTAL':
                pair_x = cell['pair']['x']
                pair_y = cell['pair']['y']
                o['pair'] = (pair_x,pair_y)
                o['name'] = cell['name']

            map_template[(x, y)] = o

        return map_template


    def reset(self, attacker: str, defender: str, seed=0):
        # 使用seed生成随机数
        random.seed(seed)

        # 初始化agents和map
        self.attacker = attacker
        self.defender = defender
        self.agents = {}
        self.map: Dict[Tuple[int,int],Dict] = {}
        self.steps = 0
        self.rand = random.Random(seed)
        self.attacker_time_used = 0
        self.defender_time_used = 0
        self.logs = []

        agent_id = 0
        

        for pos, obj in self.map_template.items():
            ty = obj['type']
            if ty == CellType.POWERUP:
                # 随机选择一个powerup
                powerup = self.rand.choice(list(Powerup))
                self.map[pos] = {'type': CellType.POWERUP, 'powerup': powerup}
            
            elif ty == CellType.COIN:
                self.map[pos] =  {'type': CellType.COIN, 'score': self.map_conf['coin_score']}

            elif ty == CellType.ATTACKER:
                attacker_agent = Agent(agent_id, pos, Agent.ATTACKER, attacker,self.map_conf['vision_range'])
                self.agents[agent_id] = attacker_agent
                agent_id += 1
                
            elif ty == CellType.DEFENDER:
                defender_agent = Agent(agent_id, pos, Agent.DEFENDER, defender,self.map_conf['vision_range'])
                self.agents[agent_id] = defender_agent
                agent_id += 1

            else:
                self.map[pos] = obj    


    def _check_out_of_bounds(self, agent: Agent) -> bool:
        x, y = agent.next_pos
        map_width = self.map_conf['width']
        map_height = self.map_conf['height']
        return x < 0 or x >= map_width or y < 0 or y >= map_height
        

    def _check_collision_between_agents(self, agent1: Agent, agent2: Agent) -> str:
        if agent1.next_pos == agent2.next_pos:
            return "dest"
        if agent1.next_pos == agent2.pos and agent2.next_pos == agent1.pos:
            return "path"


    def _handle_powerup(self, agent: Agent, cell: Dict) -> None:
        #处理获得道具的逻辑

        powerup_type = cell['powerup']
        if agent.role == agent.DEFENDER and powerup_type == Powerup.INVISIBILITY:
            self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]获得隐身道具")
            agent.powerups["invisibility"] = self.powerup_conf['invisibility']['duration']
            del self.map[agent.next_pos]
        elif agent.role == agent.DEFENDER and powerup_type == Powerup.SHIELD:
            self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]获得防守道具")
            agent.powerups["shield"] = self.powerup_conf['shield']['duration']
            del self.map[agent.next_pos]
        elif agent.role == agent.ATTACKER and powerup_type == Powerup.SWORD:
            self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]获得攻击道具")
            agent.powerups["sword"] = self.powerup_conf['sword']['duration']
            del self.map[agent.next_pos]
        elif powerup_type == Powerup.PASSWALL:
            self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]获得穿墙道具")
            agent.powerups["passwall"] = self.powerup_conf['passwall']['duration']
            del self.map[agent.next_pos]
        elif powerup_type == Powerup.EXTRAVISION:
            self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]获得视野扩展道具")
            agent.vision_range = self.powerup_conf['extravision']['extra']
            agent.powerups["extravision"] = self.powerup_conf['extravision']['duration']
            del self.map[agent.next_pos]



    def _handle_coin(self, agent: Agent, cell: Dict) -> None:
        #处理获得金币的逻辑
        if agent.role != Agent.ATTACKER:
            agent.score += self.map_conf['coin_score']  # 加分逻辑
            self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]获得金币")
            # 删除地图上的这个金币
            del self.map[agent.next_pos]


    # def _find_spawn_pos(self, agent):
    #     for pos, cell in self.map_template.items():
    #         ty = cell['type']
    #         if (agent.role == agent.ATTACKER and ty == CellType.ATTACKER) or \
    #         (agent.role == Agent.DEFENDER and ty == CellType.ATTACKER):
    #             if pos not in [agent.next_pos for agent in self.agents.values()]:
    #                 return pos
    #     raise Exception("No available spawn position found.")


    def _handle_agent_collision_different_team(self, collision_type:str,attacker: Agent,defender: Agent):
        if defender.powerups.get("shield") and not attacker.powerups.get("sword"):
            return

        if defender.invulnerability_duration > 0:
            return
        
        
        if attacker.powerups.get("sword"):
            # 攻击方获得防守方的分数的一半
            attacker.score += defender.score
            score_delta = defender.score
            defender.score = 0
        else:
            attacker.score += defender.score // 2
            score_delta = defender.score // 2
            defender.score //= 2

        #回到起始地点
        self.logs.append(f"player[{attacker.player_id}]的agent[{attacker.id}]抓获player[{defender.player_id}]的agent[{defender.id}],抢夺了{score_delta}金币")
        defender.next_pos = defender.origin_pos
        defender.invulnerability_duration = self.map_conf['invulnerability_duration']


    # def _handle_agent_collision_different_team(self, collision_type:str,attacker: Agent,defender: Agent):
    #     if defender.powerups.get("shield") or defender.invulnerability_duration > 0:
    #         if collision_type == "dest":
    #             #攻击方留在原地
    #             attacker.next_pos = attacker.pos
    #         elif collision_type == "path":
    #             attacker.next_pos = attacker.pos
    #             defender.next_pos = defender.pos

    #     else:
    #         # 攻击方获得防守方的分数的一半
    #         attacker.score += defender.score // 2
    #         defender.score //= 2
    #         defender.next_pos = self._find_spawn_pos(defender)  # 设为出生位置
    #         defender.invulnerability_duration = self.map_conf['invulnerability_duration']


    def _handle_agent_collision_same_team(self, collision_type:str,agent_a: Agent,agent_b: Agent):
        if collision_type == "dest": #目的地碰撞,这id小的优先
            if agent_a.id < agent_b.id:
                agent_b.next_pos = agent_b.pos
            else:
                agent_a.next_pos = agent_a.pos
            
        elif collision_type == "path": #路径碰撞，均不成功
            agent_a.next_pos = agent_a.pos
            agent_b.next_pos = agent_b.pos

    def _move(self, agent: Agent, direction: Direction) -> None:
        """根据给定的方向移动agent"""
        x, y = agent.pos
        if direction == Direction.UP:
            agent.next_pos = (x, y - 1)
        elif direction == Direction.DOWN:
            agent.next_pos = (x, y + 1)
        elif direction == Direction.LEFT:
            agent.next_pos = (x - 1, y)
        elif direction == Direction.RIGHT:
            agent.next_pos = (x + 1, y)
        else:
            agent.next_pos = (x, y)

    def _get_agents(self,role: str) -> List[Agent]:
        agents = []
        for agent_id, agent in self.agents.items():
            if agent.role == role:
                agents.append(agent)
        agents = sorted(agents,key = lambda x: x.id)
        return agents


    def _refresh_powerups(self):
        refresh_interval = self.map_conf.get('refresh_interval',0)
        if self.steps >= 0 and refresh_interval > 0 and self.steps % refresh_interval == 0:
            for pos, obj in self.map_template.items():
                ty = obj['type']
                if ty == CellType.POWERUP and pos not in self.map:
                    # 随机选择一个powerup
                    powerup = self.rand.choice(list(Powerup))
                    self.map[pos] = {'type': CellType.POWERUP, 'powerup': powerup}


    def apply_actions(self,attacker_actions: Dict[int, str],defender_actions: Dict[int, str],attacker_time_used = 0,defender_time_used = 0) -> None:
        self.logs = []
        self.steps += 1
        self.attacker_time_used += attacker_time_used
        self.defender_time_used += defender_time_used

        #刷新道具
        self._refresh_powerups()

        #更新道具和无敌状态持续时间
        for agent in self.agents.values():
            self._reduce_powerup_duration(agent)
            if agent.invulnerability_duration > 0:
                agent.invulnerability_duration -= 1

        attacker_agents = self._get_agents(Agent.ATTACKER)
        defender_agents = self._get_agents(Agent.DEFENDER)

        #用动作更新next_pos位置
        for agents,actions in [(attacker_agents,attacker_actions),(defender_agents,defender_actions)]:
            for agent in agents:
                try:
                    act = Direction[actions[int(agent.id)]]
                    self._move(agent,act)
                except KeyError as e:
                    logger.error("key error:%s",e)


        #检测越界、撞墙与传送门
        for agent in chain_agents(defender_agents,attacker_agents):
            #检测越界
            if self._check_out_of_bounds(agent):
                self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]尝试越界")
                agent.next_pos = agent.pos

            cell = self.map.get(agent.next_pos)
            if not cell:
                continue

            #检测穿墙，考虑穿墙道具的效果
            if not agent.powerups.get("passwall") and cell['type'] == CellType.WALL:
                self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]尝试撞墙")
                agent.next_pos = agent.pos

            #检测是否传送
            if cell['type'] == CellType.PORTAL:
                self.logs.append(f"player[{agent.player_id}]的agent[{agent.id}]传送到{cell['pair']}")
                agent.next_pos = cell['pair']


        # #处理相同队伍内agent之间的碰撞
        # for agents in [attacker_agents,defender_agents]:
        #     for agent in agents:
        #         for other_agent in agents:
        #             if other_agent.id == agent.id:
        #                 continue
        #             agent_collision = self._check_collision_between_agents(agent, other_agent)
        #             if not agent_collision:
        #                 continue
        #             self._handle_agent_collision_same_team(agent_collision)


        #检测agent与道具和金币的碰撞，优先处理defender
        for agent in chain_agents(defender_agents,attacker_agents):
            cell = self.map.get(agent.next_pos)
            if not cell:
                continue
            if cell['type'] == CellType.COIN:
                #处理获得金币
                self._handle_coin(agent, cell)
            elif cell['type'] == CellType.POWERUP:
                # 处理获得道具...
                self._handle_powerup(agent, cell)


        #检测不同队伍agent之间的碰撞
        for a in attacker_agents:
            for d in defender_agents:
                agent_collision = self._check_collision_between_agents(a, d)
                if not agent_collision:
                    continue
                self._handle_agent_collision_different_team(agent_collision,a,d)


        #最后更新所有agent的pos
        for agent in chain_agents(defender_agents,attacker_agents):
            agent.pos = agent.next_pos



    def _reduce_powerup_duration(self, agent: Agent) -> None:
        for powerup in list(agent.powerups):
            agent.powerups[powerup] -= 1
            if agent.powerups[powerup] <= 0:
                if powerup == 'extravision':
                    agent.vision_range = self.map_conf['vision_range']
                del agent.powerups[powerup]


    def get_result(self) -> Dict:
        scores = defaultdict(lambda : 0)
        for agent in self.agents.values():
            scores[agent.player_id] += agent.score

        return {
            "players": [
                {
                    "id": self.attacker,
                    "role": "ATTACKER",
                    "score": scores[self.attacker],
                    "time_used": self.attacker_time_used
                },
                {
                    "id": self.defender,
                    "role": "DEFENDER",
                    "score": scores[self.defender],
                    "time_used": self.defender_time_used
                }
            ],
            "steps": self.steps,
        }

        # "time_used": {
        #     self.attacker: self.attacker_time_used,
        #     self.defender: self.defender_time_used,
        # }

        # "roles": {
        #     self.attacker: "ATTACKER",
        #     self.defender: "DEFENDER"
        # },
        # "scores": scores,


    def get_agent_states_by_player(self,player: str) -> Dict:
        #返回属于某个player的所有agent的视野范围内所有地图的状态，包括墙体，道具，金币，agent等
        agent_states = defaultdict(list)

        for agent in self.agents.values():
            state = agent.__dict__.copy()
            del state['next_pos']
            del state['origin_pos']
            pos = state.pop('pos')
            state["x"] = pos[0]
            state["y"] = pos[1]
            agent_states[pos].append(state)

        views = {}

        for agent in self.agents.values():

            if agent.player_id != player:
                continue

            view = {
                "walls":[],
                "portals": [],
                "powerups": [],
                "coins": [],
                "other_agents": []
            }

            x, y = agent.pos
            vision_range = agent.vision_range
            for dx in range(-vision_range, vision_range + 1):
                for dy in range(-vision_range, vision_range + 1):
                    vx,vy = x+dx, y+dy

                    #find in map
                    cell = self.map.get((vx,vy))
                    if cell is not None:
                        if cell['type'] == CellType.COIN:
                            view['coins'].append({
                                "x": vx,
                                "y": vy,
                                "score": cell['score']
                            })

                        elif cell['type'] == CellType.PORTAL:
                            view['portals'].append({
                                "x": vx,
                                "y": vy,
                                "pair": {
                                    "x": cell['pair'][0],
                                    "y": cell['pair'][1]
                                },
                                "name": cell.get('name') 

                            })
                        elif cell['type'] == CellType.WALL:
                            view['walls'].append({
                                "x": vx,
                                "y": vy,
                            })

                        elif cell['type'] == CellType.POWERUP:
                            view['powerups'].append({
                                "x": vx,
                                "y": vy,
                                "powerup": str(cell['powerup'])
                            })

                    #find in agents
                    ss = agent_states[vx,vy]
                    for s in ss:
                        if s['id'] == agent.id:
                            view['self_agent'] = s
                        else:
                            if agent.role == agent.ATTACKER and 'invisibility' in s['powerups']:
                                continue
                            view["other_agents"].append(s)

            views[agent.id] = view

        return views

    def get_logs(self):
        return self.logs

    def is_over(self) -> bool:
        """检查游戏是否结束"""
        # 判断是否达到最大回合数
        if self.steps >= self.map_conf['max_steps']:
            return True

        # 判断是否所有金币被吃完
        for cell in self.map.values():
            if cell['type'] == CellType.COIN:
                return False

        return True


    def get_map_states(self) -> Dict:
        #从全局视觉，返回地图中所有元素的状态，包括墙体，道具，金币，agent等
        """
        返回对象如下:
        {
            "agents": [
                {     
                    "id": agent_id //agent_id
                    "x": 1, //x坐标
                    "y": 1, //y坐标
                    "powerups": { //所有持有道具的持续状态，没持有某个道具，则key不存在,value为持续时间
                        "invisibility": 5,
                        "passwall": 2,
                        "extravision": 3,
                        "shield": 6,
                        "sword": 4
                    }  # 当前持有的道具
                    "role": role  //agent当前角色，ATTACKER 或 DEFENDER
                    "player_id" : player_id //用户id
                    "vision_range" : 5 //视野范围
                    "score" : 0 //持有的分数
                    "invulnerability_duration" : 0 //无敌的回合
                },
                ...
            ],
            "walls": [
                {"x": 0,"y": 1},
                ...
            ],
            "portals": [
                {"x": 0,"y": 1,"pair": {"x":3,"y":4},"name": "A"},
                ...
            ],
            "powerups": [
                {"x": 0,"y": 5,"powerup": "invisibility"},
                ...
            ],
            "coins": [
                {"x": 0,"y": 5,"score": 6},
                ...
            ]
        }
        """
        map_state = {
            "agents": [],
            "walls": [],
            "portals": [],
            "powerups": [],
            "coins": []
        }
        
        for pos, cell in self.map.items():
            if cell['type'] == CellType.WALL:
                map_state["walls"].append({"x": pos[0], "y": pos[1]})
            elif cell['type'] == CellType.PORTAL:
                map_state["portals"].append({
                    "x": pos[0],
                    "y": pos[1],
                    "pair": {
                        "x": cell['pair'][0],
                        "y": cell['pair'][1],
                    },
                    "name": cell.get('name')  
                })
            elif cell['type'] == CellType.POWERUP:
                map_state["powerups"].append({
                    "x": pos[0], 
                    "y": pos[1],
                    "powerup": str(cell['powerup'])
                })
            elif cell['type'] == CellType.COIN:
                map_state["coins"].append({
                    "x": pos[0],
                    "y": pos[1],
                    "score": cell.get('score', self.map_conf['coin_score']) 
                })
                
        for agent in self.agents.values():
            map_state["agents"].append({
                "id": agent.id,
                "x": agent.pos[0],
                "y": agent.pos[1],
                "powerups": agent.powerups.copy(),
                "role": agent.role,
                "player_id": agent.player_id,
                "vision_range": agent.vision_range,
                "score": agent.score,
                "invulnerability_duration": agent.invulnerability_duration
            })
            
        return map_state


    