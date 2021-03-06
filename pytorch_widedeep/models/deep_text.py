import numpy as np
import torch
import warnings

from torch import nn
from ..wdtypes import *
from .deep_dense import dense_layer


class DeepText(nn.Module):
    r"""Standard text classifier/regressor comprised by a stack of RNNs (LSTMs).
    In addition, there is the option to add a Fully Connected (FC) set of dense
    layers (FC-Head, referred as 'texthead') on top of the stack of RNNs

    Parameters
    ----------
    vocab_size: Int
        number of words in the vocabulary
    hidden_dim: Int
        number of features in the hidden state h of the LSTM
    n_layers: Int
        number of recurrent layers
    rnn_dropout: Int
        dropout for the dropout layer on the outputs of each LSTM layer except
        the last layer
    bidirectional: Boolean
        indicates whether the staked RNNs are bidirectional
    padding_idx: Int
        index of the padding token in the padded-tokenised sequences. default:
        1. I use the fastai Tokenizer where the token index 0 is reserved for
        the  unknown word token
    embed_dim: Int, Optional
        Dimension of the word embedding matrix
    embedding_matrix: np.ndarray, Optional
         Pretrained word embeddings
    head_layers: List, Optional
        List with the sizes of the stacked dense layers in the head
        e.g: [128, 64]
    head_dropout: List, Optional
        List with the dropout between the dense layers. e.g: [0.5, 0.5].
    head_batchnorm: Boolean, Optional
        Whether or not to include batch normalizatin in the dense layers that
        form the texthead

    Attributes
    ----------
    word_embed: nn.Module
        word embedding matrix
    rnn: nn.Module
        Stack of LSTMs
    texthead: nn.Sequential, Optional
        Stack of dense layers
    output_dim: Int
        The output dimension of the model. This is a required attribute
        neccesary to build the WideDeep class

    Example
    --------
    >>> import torch
    >>> from pytorch_widedeep.models import DeepText
    >>> X_text = torch.cat((torch.zeros([5,1]), torch.empty(5, 4).random_(1,4)), axis=1)
    >>> model = DeepText(vocab_size=4, hidden_dim=4, n_layers=1, padding_idx=0, embed_dim=4)
    >>> model(X_text)
    tensor([[ 0.0315,  0.0393, -0.0618, -0.0561],
            [-0.0674,  0.0297, -0.1118, -0.0668],
            [-0.0446,  0.0814, -0.0921, -0.0338],
            [-0.0844,  0.0681, -0.1016, -0.0464],
            [-0.0268,  0.0294, -0.0988, -0.0666]], grad_fn=<SelectBackward>)
    """
    def __init__(self,
        vocab_size:int,
        hidden_dim:int=64,
        n_layers:int=3,
        rnn_dropout:float=0.,
        bidirectional:bool=False,
        padding_idx:int=1,
        embed_dim:Optional[int]=None,
        embedding_matrix:Optional[np.ndarray]=None,
        head_layers:Optional[List[int]] = None,
        head_dropout:Optional[List[float]]=None,
        head_batchnorm:Optional[bool] = False):
        super(DeepText, self).__init__()

        if embed_dim is not None and embedding_matrix is not None and not embed_dim==embedding_matrix.shape[1]:
            warnings.warn(
                'the input embedding dimension {} and the dimension of the '
                'pretrained embeddings {} do not match. The pretrained embeddings '
                'dimension ({}) will be used'.format(embed_dim, embedding_matrix.shape[1],
                    embedding_matrix.shape[1]), UserWarning)

        self.bidirectional = bidirectional
        self.head_layers = head_layers

        # Pre-trained Embeddings
        if isinstance(embedding_matrix, np.ndarray):
            self.word_embed = nn.Embedding(vocab_size, embedding_matrix.shape[1], padding_idx = padding_idx)
            self.word_embed.weight = nn.Parameter(torch.Tensor(embedding_matrix))
            embed_dim = embedding_matrix.shape[1]
        else:
            self.word_embed = nn.Embedding(vocab_size, embed_dim, padding_idx = padding_idx)

        # stack of RNNs (LSTMs)
        self.rnn = nn.LSTM(embed_dim,
            hidden_dim,
            num_layers=n_layers,
            bidirectional=bidirectional,
            dropout=rnn_dropout,
            batch_first=True)

        # the output_dim attribute will be used as input_dim when "merging" the models
        self.output_dim = hidden_dim*2 if bidirectional else hidden_dim

        if self.head_layers is not None:
            assert self.head_layers[0]==self.output_dim, (
                "The hidden dimension from the stack or RNNs ({}) is not consistent with "
                "the expected input dimension ({}) of the fc-head".format(
                    self.output_dim, self.head_layers[0]))
            if not head_dropout: head_dropout = [0.]*len(head_layers)
            self.texthead = nn.Sequential()
            for i in range(1, len(head_layers)):
                self.texthead.add_module(
                    'dense_layer_{}'.format(i-1),
                    dense_layer(head_layers[i-1], head_layers[i], head_dropout[i-1], head_batchnorm)
                    )
            self.output_dim = head_layers[-1]

    def forward(self, X:Tensor)->Tensor:

        embed = self.word_embed(X.long())
        o, (h, c) = self.rnn(embed)
        if self.bidirectional:
            last_h = torch.cat((h[-2], h[-1]), dim = 1)
        else:
            last_h = h[-1]
        if self.head_layers is not None:
            out = self.head(last_h)
            return out
        else:
            return last_h