-- Why an image was not processed: download failed, corrupt file, near-duplicate of another.
-- Silent failures are how a pipeline quietly loses data, so every non-'done' outcome says why.
alter table media_items add column status_note text;
