# Lossless compression - an encoder and decoder

The objective of this assignment was to develop an encoder and decoder for lossless compression of LATEXfiles, receiving a .tex document as input and outputting a compressed .lz file. Note the assignment objective is compression size oriented, as opposed to compression speed. As a result, the ideas implemented have often required a speed trade-off.

Our approach recognises the need to exploit statistical and structural redundancy, exploring how to achieve this most effectively. The foundational methods build upon in the algorithm are Lempel-Ziv-77 and Arithmetic Coding. 

⋅⋅* Lempel-Ziv (LZ) algorithms are renowned for reducing structural redundancy
⋅⋅* Arithmetic coding (AC) works to eliminate statistical redundancy. 


Our full report(./Codes.pdf) assumes basic understanding of these compression strategies and build off this groundwork knowledge.

Find the encoder implemented in Python [here](./encoder.py).
Find the decoder implemented in Python [here](./decoder.py).
