### -*-coding:utf-8-*-
import sys
import csv
import numpy as np

from keras.layers import Input, Dense, Reshape, Flatten, Dropout
from keras.layers import BatchNormalization, Activation, ZeroPadding2D
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling2D, Conv2D
from keras.models import Sequential, Model
from keras.optimizers import Adam
from keras.initializers import RandomUniform
import warnings

warnings.simplefilter('ignore', np.RankWarning)

# GreedyNN_MultiPoint
class GreedyNN_MP_RAND():
	def __init__(self, img_shape, n_gen_img, evaluator, noise_dim = 100, fixed_noise = False, filepath = None):
		self.img_shape = img_shape
		self.n_gen_img = n_gen_img
		self.noise_dim = noise_dim
		self.evaluator = evaluator
		self.fixed_noise = fixed_noise
		self.filepath = filepath

		optimizer = Adam(0.001, 0.9)

		# Generator model
		self.generator = self.build_generator()
		self.generator.compile(loss='mean_absolute_error', optimizer=optimizer)

	def build_generator(self):
		noise_shape = (self.noise_dim,)
		n_unit = self.img_shape[0] * self.img_shape[1]
		model = Sequential()

		model.add(Dense(n_unit, input_shape=noise_shape))
		model.add(LeakyReLU(alpha=0.2))
		model.add(BatchNormalization(momentum=0.8))
		model.add(Dense(n_unit))
		model.add(LeakyReLU(alpha=0.2))
		model.add(BatchNormalization(momentum=0.8))
		model.add(Dense(n_unit))
		model.add(LeakyReLU(alpha=0.2))
		model.add(BatchNormalization(momentum=0.8))
		model.add(Dense(np.prod(n_unit), activation='linear', kernel_initializer=RandomUniform(-1,1)))
		model.add(Reshape(self.img_shape))

		model.summary()

		return model

	def train(self, n_epoch, batch_size=64):
		n_batches = self.n_gen_img // batch_size // self.img_shape[0]
		print('Number of batches:', n_batches)
		best_fitness = np.NINF
		best_img = np.random.uniform(-1.0, 1.0, (self.img_shape[1]))
		noise = np.random.normal(0, 1, (batch_size, self.noise_dim))
		max_n_eval = n_epoch * self.n_gen_img
		n_eval = 0
		g_loss = 1.0

		if self.filepath:
			f = open(self.filepath, mode = "w")
			csv_writer = csv.writer(f)
			csv_writer.writerow([
				"n_eval",
				"max_n_eval",
				"dist_mean",
				"dist_stddev",
				"train_loss",
				"fitness_mean",
				"fitness_best",
				"fitness_best_so_far",
			])

		while n_eval < max_n_eval:
			for iteration in range(n_batches):
				# ---------------------
				#  Generator learning
				# ---------------------
				# pickup images from generator
				if not self.fixed_noise:
					noise = np.random.normal(0, 1, (batch_size, self.noise_dim))
				gen_imgs = self.generator.predict(noise)
				randomly_gen_size = np.int(batch_size * min(g_loss, 1.0))
				randomly_gen_imgs = np.random.rand(randomly_gen_size, gen_imgs.shape[1], gen_imgs.shape[2]) * 2 - 1
				gen_imgs = np.vstack((gen_imgs, randomly_gen_imgs))
				gen_imgs_fitness = np.apply_along_axis(self.evaluator, 2, gen_imgs)
				n_eval += gen_imgs.shape[0] * gen_imgs.shape[1]

				# swap
				# best_index = np.argmax(gen_imgs_fitness)
				# best_index = np.unravel_index(np.argmax(gen_imgs_fitness), gen_imgs_fitness.shape)
				ascending_indice = np.unravel_index(np.argsort(gen_imgs_fitness.flatten()), gen_imgs_fitness.shape)
				if gen_imgs_fitness[ascending_indice][-1] > best_fitness:
					best_fitness = gen_imgs_fitness[ascending_indice][-1]
					best_img = gen_imgs[ascending_indice][-1]

				# Train the generator
				x_len = self.img_shape[1] * 2 + 1
				x = np.ones((gen_imgs.shape[0] * gen_imgs.shape[1], x_len), float)
				for i in range(self.img_shape[1]):
					x[:, i*2] = gen_imgs[:, :, i].flatten()
					x[:, i*2+1] = gen_imgs[:, :, i].flatten() ** 2

				# 近似
				fitness_pred_error = np.copy(gen_imgs_fitness)
				for i in range(x_len):
					p = np.polyfit(x[:, i], gen_imgs_fitness.flatten(), 2)
					p[0] = max(p[0], 0)
					y_pred = (p[0] * x[:, i] ** 2 + p[1] * x[:, i] + p[2]) / x.shape[1]
					fitness_pred_error -= np.reshape(y_pred, fitness_pred_error.shape)
				error_ascending_indice = np.unravel_index(np.argsort(fitness_pred_error.flatten()), fitness_pred_error.shape)

				y_raw = gen_imgs[error_ascending_indice][-(self.img_shape[0]):]
				best_index_in_y_raw = np.where((y_raw == best_img).all(axis = 1))
				if len(best_index_in_y_raw[0]) == 0:
					y_raw = y_raw[:-1]
				else:
					y_raw = np.delete(y_raw, best_index_in_y_raw[0], 0)
				y_raw = np.append([best_img], y_raw, axis=0)
				y = np.tile(y_raw, (batch_size, 1, 1))
				g_loss = self.generator.train_on_batch(noise, y)

				# progress
				# print ("epoch:%d, iter:%d,  [D loss: %f, acc.: %.2f%%] [G loss: %f]" % (epoch, iteration, d_loss[0], 100*d_loss[1], g_loss))
				print ("epoch:%d/%d, iter:%d/%d, [G loss: %f] [mean: %f best: %f]" %
					(n_eval, max_n_eval, iteration+1, n_batches, g_loss, np.mean(gen_imgs_fitness), best_fitness))

				print(f"{n_eval}/{max_n_eval}, {iteration+1}/{n_batches} fitness:{np.mean(gen_imgs_fitness)}, {best_fitness}")

				mean = np.mean(gen_imgs, axis=0)
				stddev = np.std(gen_imgs, axis=0)
				print("mean:", np.mean(mean), ", stddev:", np.mean(stddev))

				# print([self.evaluator(d) for d in gen_imgs], train_img_fitness[0])

				if self.filepath:
					csv_writer.writerow([
						n_eval,
						max_n_eval,
						np.mean(mean),
						np.mean(stddev),
						g_loss,
						np.mean(gen_imgs_fitness),
						gen_imgs_fitness[ascending_indice][-1],
						best_fitness,
					])

		print(best_fitness)
		if self.filepath:
			f.close()
		return best_fitness

if __name__ == '__main__':
	def sphere(x):
		return -np.sum(x ** 2)

	def sphere_offset(x):
		return -np.sum((x - 0.5) ** 2)

	def ackley(x):
		x *= 32.768
		return -(20 - 20 * np.exp(- 0.2 * np.sqrt(1.0 / len(x) * np.sum(x ** 2))) +\
			np.e - np.exp(1.0 / len(x) * np.sum(np.cos(2 * np.pi * x))))

	def rastrigin(x):
		x *= 5.12
		return -10 * len(x) - np.sum(x ** 2) + 10 * np.sum(np.cos(2 * np.pi * x))

	nn = GreedyNN_MP_RAND(
		img_shape = (3, 5),
		n_gen_img = 50,
		evaluator = sphere_offset,
		noise_dim = 1,
		fixed_noise=True)
	best_fitness = nn.train(n_epoch=100, batch_size=10)
	print(best_fitness)