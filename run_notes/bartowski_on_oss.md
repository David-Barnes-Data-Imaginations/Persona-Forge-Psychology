# Notes by Bartowski from LM Studio:
---
## Mini Technical Deep Dive
### Sliding window attention
You may have seen the attention equation before, commonly credited with being the "secret sauce" that makes Transformers so powerful:

Attention(Q, K, V) = softmax(QK^T/sqrt(d))V

- We call this full attention, as the model gets to pay attention over the whole input: since Q, K, and V are functions of the whole input, the model gets access to all the tokens in the sequence. 
- This makes attention supremely powerful, but it has the unfortunate side effect that Q, K, and V will get larger as your chat gets longer. 
- This means that once your chat grows into the thousands of tokens, it takes more computations to compute attention, which manifests in increased memory usage and slower response speeds. 
- In fact, this increase is quadratic, which means that doubling your chat length will make the model take about four times longer to respond!
- This isn't great for on-device AI, since nobody wants to sit around for half an hour waiting for a response. 
- Sliding window attention addresses this issue by only using the input embeddings for a sliding window of the last W tokens (where W depends on the model), which means that Q, K, and V are capped at a fixed size, and thus so are the memory usage and compute requirements. 
- This way, no matter how long the chat is, the model won't take absurdly long to respond or eat up all your computer's memory.

- Sounds great, right? One problem: if the whole model used sliding window attention, it wouldn't see anything outside its small sliding window, so it would forget about your earlier chats! A model with memory loss is no fun, so OpenAI uses a 50/50 split between full attention and sliding window attention in this model to get the best of both worlds: knowledge of the whole input, but also more efficient processing than other models.

### Attention sinks
Let's take a look at this part of the attention operation:

softmax(QK^T/sqrt(d))

- The matrix QK^T contains the attention scores: a quantification of how much attention each token wants to pay to each other token. 
- A model might put high scores on a load-bearing word like a subject or verb, and low scores on a particle like "the". 
- In order to determine the information that flows to the next part of the model, the model wants to extract some combination of the values stored in V using these attention scores. 
- To do this while making sure the numbers don't blow out of proportion, the model applies a softmax operation, which makes all the outbound scores for a token sum to 1.
- But what if the model doesn't want to pay attention to any token in particular? 
- The softmax still forces the scores to sum to 1, which forces the model to pay excess attention to unimportant tokens! 
- These excess attention scores typically pool in the earliest tokens in the sequence, called attention sinks. 
- This poses an issue for sliding window attention: when those tokens leave the sliding window, all that excess attention gets distributed to other tokens, causing the model to pay extra attention to nothing at all! 
- This phenomenon has been found to cause LLM response quality to significantly degrade on long conversations or long input prompts.

- _Xiao et al_ solve this using custom tokens for the attention sinks, which are appended to the attention scores but not used when extracting information from V. 
- This allows the excess attention to pool in the sink tokens and not affect the attention output, preventing quality degradation.
- OpenAI has adopted this in their GPT OSS model, which allows the model to accurately respond to queries that are millions of tokens long or continue conversations for hours on end!


---