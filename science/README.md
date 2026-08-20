# vNext science graph

The science layer converts provider-specific literature retrieval into reproducible discovery candidates. It does not convert search results into canonical scientific claims.

The pipeline is:

`frozen query protocol -> provider adapter -> acquisition freeze -> provider-attributed candidate -> exact-identifier resolution -> relevance adjudication -> later canonical graph projection`

Cross-provider metadata is preserved until identity resolution is explicit. DOI, PMID, PMCID, and OpenAlex identifiers use the vNext identity contract. Similar title or author strings can create a resolution candidate only.

Raw provider responses remain outside Git. A committed acquisition freeze records request identity, provider/source state, response-manifest digest, exhaustion state, observed count, and the content-addressed storage class. A partial or failed traversal cannot be represented as complete.

The first protocol prioritizes 2015 through the declared evidence cutoff for operational acquisition, then backfills 2000–2014 and earlier work in separate immutable freezes. Priority windows control work order and do not rank scientific importance.

`STATUS=FROZEN_PROTOCOL_NO_PRODUCTION_ACQUISITION_YET` is intentional until real provider bytes have been retrieved and their manifests verified.
