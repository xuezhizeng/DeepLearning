# coding=utf-8
# These are all the modules we'll be using later. Make sure you can import them
# before proceeding further.
from __future__ import print_function
import collections
import math
import numpy as np
import os
import random
import tensorflow as tf
import zipfile
from matplotlib import pylab
from six.moves import range
from six.moves.urllib.request import urlretrieve
from sklearn.manifold import TSNE


def read_data(filename):
    """Extract the first file enclosed in a zip file as a list of words"""
    with zipfile.ZipFile(filename) as f:
        data = tf.compat.as_str(f.read(f.namelist()[0])).split()
    return data

words = read_data("text8.zip")
print('Data size %d' % len(words))

vocabulary_size = 50000


def build_dataset(words):
    """
    从词库中抽取出出现次数最多的vocabulary_size个词，并将这vocabulary_size个词进行编号，编号后按照此编号对词库中的所有的词建立索引，
    词库中没有的词索引为0。
    :param words: 词库
    :return:
    """
    count = [['UNK', -1]]
    # 词库中的字数统计，并且取其中出现次数最多的vocabulary_size个词。
    count.extend(collections.Counter(words).most_common(vocabulary_size - 1))
    dictionary = dict()
    # 创建词索引，为vocabulary_size个词按照出现次数从大到小编号，存为字典格式。创建词汇表
    for word, _ in count:
        dictionary[word] = len(dictionary)
    # 用于存放词的索引
    data = list()
    unk_count = 0
    # 对词库中的每个词按照dictionary中的索引进行编号， 如果没有出现的词则都标为0。即低频词汇使用UNK替换。
    for word in words:
        if word in dictionary:
            index = dictionary[word]
        else:
            # 不在词典中的词定义为UNK
            index = 0  # dictionary['UNK']
            unk_count += 1
        data.append(index)

    count[0][1] = unk_count
    # 转换成[编号，词]对， 逆词汇表
    reverse_dictionary = dict(zip(dictionary.values(), dictionary.keys()))
    return data, count, dictionary, reverse_dictionary

data, count, dictionary, reverse_dictionary = build_dataset(words)
print('Most common words (+UNK)', count[:5])
print('Sample data', data[:10])
print('Sample reverse_dictionary', [reverse_dictionary[i] for i in data[:10]])
del words  # Hint to reduce memory.

data_index = 0


def generate_batch(batch_size, num_skips, skip_window):
    """
    batch_size是指一次扫描多少块，skip_window为左右上下文取词的长短，num_skips输入数字的重用次数。
    :param batch_size:
    :param num_skips:
    :param skip_window:
    :return:
    """
    global data_index
    assert batch_size % num_skips == 0
    assert num_skips <= 2 * skip_window
    # 用来存放每个bantch的数据
    batch = np.ndarray(shape=(batch_size), dtype=np.int32)
    labels = np.ndarray(shape=(batch_size, 1), dtype=np.int32)
    span = 2 * skip_window + 1  # [ skip_window target skip_window ]
    # 新建一个双向链表，长度为span
    buffer = collections.deque(maxlen=span)
    for _ in range(span):
        buffer.append(data[data_index])
        data_index = (data_index + 1) % len(data)

    print('data_index', data_index)
    print('buffer_init:')
    for i in buffer:
        print(reverse_dictionary[i],)

    for i in range(batch_size // num_skips):
        target = skip_window  # target label at the center of the buffer
        targets_to_avoid = [skip_window]
        print('target_int, target_to_avoid_init', target, targets_to_avoid)
        for j in range(num_skips):
            while target in targets_to_avoid:
                target = random.randint(0, span - 1)
                print('target_runing', target)
            targets_to_avoid.append(target)
            print('targets_to_avoid_runing', targets_to_avoid)
            batch[i * num_skips + j] = buffer[skip_window]
            labels[i * num_skips + j, 0] = buffer[target]
        buffer.append(data[data_index])
        print('buffer______runing')
        for k in buffer:
            print(reverse_dictionary[k],)
        data_index = (data_index + 1) % len(data)
        print('data_index', data_index)
    return batch, labels

print('data:', [reverse_dictionary[di] for di in data[:16]])

for num_skips, skip_window in [(2, 1), (4, 2)]:
    batch, labels = generate_batch(batch_size=8, num_skips=num_skips, skip_window=skip_window)
    print('\nwith num_skips = %d and skip_window = %d:' % (num_skips, skip_window))
    print('    batch:', [reverse_dictionary[bi] for bi in batch])
    print('    labels:', [reverse_dictionary[li] for li in labels.reshape(8)])

# for _ in range(3):
#     batch_size = 8
#     num_skips = 2
#     skip_window = 1
#     batch_data, batch_labels = generate_batch(batch_size, num_skips, skip_window)
#     print('\nwith num_skips = %d and skip_window = %d:' % (num_skips, skip_window))
#     print('    batch:', [reverse_dictionary[bi] for bi in batch_data])
#     print('    labels:', [reverse_dictionary[li] for li in batch_labels.reshape(batch_size)])

batch_size = 128
embedding_size = 128  # Dimension of the embedding vector.
skip_window = 1  # How many words to consider left and right.
num_skips = 2  # How many times to reuse an input to generate a label.
# We pick a random validation set to sample nearest neighbors. here we limit the
# validation samples to the words that have a low numeric ID, which by
# construction are also the most frequent.
valid_size = 16  # Random set of words to evaluate similarity on.
valid_window = 100  # Only pick dev samples in the head of the distribution.
valid_examples = np.array(random.sample(range(valid_window), valid_size))
num_sampled = 64  # Number of negative examples to sample.

graph = tf.Graph()

with graph.as_default(), tf.device('/cpu:0'):
    # Input data.
    train_dataset = tf.placeholder(tf.int32, shape=[batch_size])
    train_labels = tf.placeholder(tf.int32, shape=[batch_size, 1])
    valid_dataset = tf.constant(valid_examples, dtype=tf.int32)

    # Variables.
    embeddings = tf.Variable(
        tf.random_uniform([vocabulary_size, embedding_size], -1.0, 1.0))
    softmax_weights = tf.Variable(
        tf.truncated_normal([vocabulary_size, embedding_size],
                            stddev=1.0 / math.sqrt(embedding_size)))
    softmax_biases = tf.Variable(tf.zeros([vocabulary_size]))

    # Model.
    # Look up embeddings for inputs.
    embed = tf.nn.embedding_lookup(embeddings, train_dataset)
    # Compute the softmax loss, using a sample of the negative labels each time.
    loss = tf.reduce_mean(
        tf.nn.sampled_softmax_loss(weights=softmax_weights, biases=softmax_biases, inputs=embed,
                                   labels=train_labels, num_sampled=num_sampled, num_classes=vocabulary_size))

    # Optimizer.
    # Note: The optimizer will optimize the softmax_weights AND the embeddings.
    # This is because the embeddings are defined as a variable quantity and the
    # optimizer's `minimize` method will by default modify all variable quantities
    # that contribute to the tensor it is passed.
    # See docs on `tf.train.Optimizer.minimize()` for more details.
    optimizer = tf.train.AdagradOptimizer(1.0).minimize(loss)

    # Compute the similarity between minibatch examples and all embeddings.
    # We use the cosine distance:
    norm = tf.sqrt(tf.reduce_sum(tf.square(embeddings), 1, keep_dims=True))
    normalized_embeddings = embeddings / norm
    valid_embeddings = tf.nn.embedding_lookup(
        normalized_embeddings, valid_dataset)
    similarity = tf.matmul(valid_embeddings, tf.transpose(normalized_embeddings))

#
# num_steps = 100001
#
# with tf.Session(graph=graph) as session:
#     tf.global_variables_initializer().run()
#     print('Initialized')
#     average_loss = 0
#     for step in range(num_steps):
#         batch_data, batch_labels = generate_batch(
#             batch_size, num_skips, skip_window)
#         feed_dict = {train_dataset : batch_data, train_labels : batch_labels}
#         _, l = session.run([optimizer, loss], feed_dict=feed_dict)
#         average_loss += l
#         if step % 2000 == 0:
#             if step > 0:
#                 average_loss = average_loss / 2000
#             # The average loss is an estimate of the loss over the last 2000 batches.
#             print('Average loss at step %d: %f' % (step, average_loss))
#             average_loss = 0
#         # note that this is expensive (~20% slowdown if computed every 500 steps)
#         if step % 10000 == 0:
#             sim = similarity.eval()
#             for i in range(valid_size):
#                 valid_word = reverse_dictionary[valid_examples[i]]
#                 top_k = 8 # number of nearest neighbors
#                 nearest = (-sim[i, :]).argsort()[1:top_k+1]
#                 log = 'Nearest to %s:' % valid_word
#                 for k in range(top_k):
#                     close_word = reverse_dictionary[nearest[k]]
#                     log = '%s %s,' % (log, close_word)
#                 print(log)
#     final_embeddings = normalized_embeddings.eval()