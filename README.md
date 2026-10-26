# Civic Newsroom primary-law corpus 001

Isolated seed corpus and explicit-citation audit. This repository does not write to the newsroom, source archive, intelligence host or GitHub Pages. Its scoped Actions token writes only here. No website integration or Solitaire modification is included.

A successful law-publication.json pins a generation containing actual original PDFs and extracted text in ordered SHA-256-addressed blob parts, authority metadata, SQLite FTS5 legal text plus a reverse-citation index, record-level coverage and explicit-reference JSONL exports. External URLs record provenance; they are not substitutes for source copies. Required seed failures block publication. Optional discovery failures remain visible in acquisition-gaps.json.

Initial acquisition scope: Wyoming Title 16; the identified Wyoming civil-rules publication; the federal Constitution publication; Georgia v. Public.Resource.Org's official slip opinion as a government-edicts research seed; and unambiguous official PDF discovery for Cheyenne UDC and two county land-use versions. This is not a complete city/county/state/federal library. No lawsuit docket ingestion is implemented yet. Commercial annotations, proprietary model-code publications and unreviewed sensitive litigation attachments are not crawled.

The audit reads all 6,065 pinned public representations from dataset build-40279333802. It detects supported explicit Wyoming statute, U.S. Code, CFR, Wyoming case, U.S. Reports and Cheyenne code citation formats. It does not identify every implied legal framework. Candidate matches to a seed PDF may be index entries or cross-references, not controlling provisions. No relationship is automatically promoted to applicability, binding precedent, a holding, misconduct or a legal conclusion.

Original PDF and extracted-text hashes are distinct. Retrieval date is not an effective date. Missing historical versions, subsequent case treatment, unsupported citation formats and absent court filings remain gaps. Pleadings and judicial findings must remain distinct in future expansion.

The generated SQLite index has laws(doc_id,text), authorities(id,metadata), and links(citation,record_id,evidence); reverse lookup uses the links citation index. Assemble legal_index_gzip parts in order, verify whole length/hash, decompress, and open SQLite. Cross-reference spans use zero-based Unicode code points with end exclusive; line bounds refer only to the pinned representation. Source citations require context and legal review.

Derived generations are append-only, with 8 MiB blob parts, a 40 MiB physical-file guard, a 32 MiB per-source acquisition limit and a cumulative 512 MiB derived-generation budget. Capacity exhaustion blocks publication rather than deleting history. No full-coverage or deployment success is claimed unless the corresponding report and release descriptor exist.
