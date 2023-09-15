
import json
from game import Game
import random

#load map
with open('map.json') as f:
    map = json.load(f)
game = Game(map)


#init game
game.reset(attacker="attacker",defender="defender",seed=random.randint(0,10000))

#game loop
while not game.is_over():

    #get game state for player:
    attacker_state = game.get_agent_states_by_player("attacker")
    defender_state = game.get_agent_states_by_player("defender")

    #apply actions for agents:
    ACTIONS = ["UP","DOWN","LEFT","RIGHT","STAY"]
    attacker_actions =  { _id: random.choice(ACTIONS) for _id in attacker_state.keys() }
    defender_actions =  { _id: random.choice(ACTIONS) for _id in defender_state.keys() }
    game.apply_actions(attacker_actions=attacker_actions,defender_actions=defender_actions)


#get game result
print("game result:\r\n",game.get_result())

