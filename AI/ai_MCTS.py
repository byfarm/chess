import copy
import numpy as np
import AI.ai as ai
import random
import math
import tensorflow as tf
from AI.neural_networks import POLICY_NETWORK, VALUE_NETWORK


class Game_Node(object):
	"""
	the game node object for each game state
	"""
	def __init__(self, game: object, move: list=None, parent_node: object=None):
		# this means do not make the policy vector unless it is a chosed leaf node because then must init all children.
		# make the policy call outside the init method
		"""
		:param game: the game state
		:param move: the move taken to reach this game state
		:param parent_node: the parent node of the game
		bitboard: the 14 layer bitboard of the game state
		value_evaluation: the value of the position from the value NN
		policy_vector: the move probabilities from the policy NN
		number_of_visits: the number of visits the mcts has made to the node
		child_nodes: the child nodes of the game node
		wins: the number of wins from this position
		"""
		self.move = move
		self.game = game
		self.parent_node = parent_node if parent_node else False

		# get the evaluation
		self.bitboard = ai.to_bits(game)
		game.check_for_checkmate()
		game.look_for_draws()
		if game.stalemate:
			if game.white_win is not None:
				self.value_evaluation = float(game.white_win)
			else:
				self.value_evaluation = 0.5
		else:
			self.value_evaluation = VALUE_NETWORK(self.bitboard).numpy()[0, 0]
		# init the policy vector
		self.policy_vector = None
		self.policy_vector_legal_moves = None

		self.number_of_visits = 0
		self.child_nodes = []
		self.visited_boards = []
		self.wins = 0
		self.terminal_game_state = False if len(self.game.legal_moves) > 0 else True

	def __repr__(self):
		return f'{self.move}'

	def make_a_move(self, move: tuple[list[tuple]]):
		for child_node in self.child_nodes:
			if move == child_node.move:
				return child_node

	def get_policy_vector(self):
		"""
		needs to return the policy vector that includes
		1. ucb1 score of each of its child nodes
		2. the output from the policy NN
		3. the value evaluation from each of its child nodes
		:return:
		"""
		# make sure the children have not already been init
		if len(self.child_nodes) == 0:
			self.init_all_children()

		evaluations, ucb1_scores = self.find_child_node_information()

		policy_network_output = POLICY_NETWORK(self.bitboard)
		policy_network_probabilities = tf.divide(policy_network_output, tf.math.reduce_sum(policy_network_output))

		number_possible_moves = len(self.game.legal_moves)

		self.policy_vector_legal_moves = evaluations + ucb1_scores + policy_network_probabilities[0, :number_possible_moves]
		self.policy_vector = tf.concat((self.policy_vector_legal_moves, tf.zeros(218 - number_possible_moves, float)), axis=0)

	def find_child_node_information(self):
		evaluations = []
		ucb1_scores = []
		for node in self.child_nodes:
			evaluations.append(node.value_evaluation)
			ucb1_scores.append(node.get_ucb1_score())

		return tf.constant(evaluations, dtype=float), tf.constant(ucb1_scores, dtype=float)

	def init_all_children(self):
		for move in self.game.legal_moves:
			new_game = copy.deepcopy(self.game)
			new_game.play_machine_move(move)
			new_node = Game_Node(new_game, move=move, parent_node=self)
			self.child_nodes.append(new_node)
			self.visited_boards.append(new_game.board)

	def random_game_simulation(self) -> bool:
		"""
		simulates a game randomly to the end
		:return game.white_win: whether white won the game. False = black won, None = draw
		"""
		game = copy.deepcopy(self.game)
		while len(game.legal_moves) > 0 and not game.stalemate:
			move = random.choice(game.legal_moves)
			game.play_machine_move(move)
			game.look_for_draws()
		game.check_for_checkmate()
		return game.white_win

	def get_ucb1_score(self, exploration_constant: float=np.sqrt(2)) -> float:
		"""
		the UCB1 score of the position from the mcts
		:param exploration_constant: the constant in the equation
		:return ucb1_score: the score from the mcts
		"""
		try:
			return self.wins / self.number_of_visits + exploration_constant * math.sqrt(math.log(self.parent_node.number_of_visits) / self.number_of_visits)
		except ZeroDivisionError:
			# as if it had looked but returned a loss
			if self.parent_node.number_of_visits > 0:
				return exploration_constant * math.sqrt(math.log(self.parent_node.number_of_visits))
			else:
				return 0

	def select_child(self, move_probabilities: list[float]) -> object:
		"""
		takes the move probabilities and returns the move with the highest one
		:param move_probabilities: the output from the policy vector
		:return best_move: the best move based on the policy vector in the position
		"""
		if len(move_probabilities) < 1:
			print(self.child_nodes)
		return self.child_nodes[tf.argmax(move_probabilities)]


def back_propagate(node: object, result: float, leaf_move_turn: str):
	"""
	back propagates through network and updates if white won or not
	:param leaf_move_turn: the color of the leaf node
	:param node: the leaf node object
	:param result: the white_wins result
	:return none
	"""
	while node:
		node.number_of_visits += 1
		if node.game.move_turn == leaf_move_turn:
			if result > 0.75:
				node.wins += 1
		else:
			if result < 0.25:
				node.wins += 1
		node = node.parent_node


def MCTS(game: object=None, starting_node: object=None, iterations: int=7) -> object:
	"""
	runs a monte carlo tree search on the current game/node
	:param game: the origin game object
	:param starting_node: if tree already init, the starting node
	:param iterations: the number of times want to run a search before returning the tree object
	:return root: the root of the search tree. will be used to find the best next move
	"""
	# check if the tree is already existing
	if starting_node is None:
		root = Game_Node(game)

	else:
		root = starting_node
		root.parent_node = False

	if root.terminal_game_state:
		return root
	root.get_policy_vector()

	# run through so many times by selecting a node, seeing if it is visited, if not then finding a new one and finding
	# the outcome of it
	for _ in range(iterations):

		# add a bit of randomness to search
		# TODO: I think the noise is added only to the root vector. all the rest is just based upon mcts search, no value or policy?
		alpha = np.full(len(root.game.legal_moves), 0.3)
		dirichlet_noise = tf.convert_to_tensor(np.random.dirichlet(alpha), dtype=tf.float32)
		noise_probabilities = root.policy_vector_legal_moves + dirichlet_noise
		selected_node = root.select_child(noise_probabilities)

		while selected_node.number_of_visits > 0:
			if selected_node.policy_vector_legal_moves is not None:
				if not selected_node.terminal_game_state:
					selected_node = selected_node.select_child(selected_node.policy_vector_legal_moves)
				else:
					break
			else:
				selected_node.get_policy_vector()

		# back propogate the result
		# self_win = selected_node.value_evaluation if selected_node.game.white_win is None else int(selected_node.game.white_win)
		self_win = selected_node.value_evaluation
		back_propagate(selected_node, self_win, selected_node.game.move_turn)
		print(f"depth: {selected_node.game.move_counter - root.game.move_counter},", f"Search number: {_+1},", f"Node score: {self_win}")

	return root



"""
I need to find the real winning state of the game, backpropogate through the entire tree and assign the result,
then try to fit it with the value netowrk
"""
