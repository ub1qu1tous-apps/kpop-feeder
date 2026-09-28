-- 009: cap the feedback board at 20 entries by BLOCKING new posts once
-- full, instead of silently dropping the oldest (008's behavior). The
-- board only has room again once the admin deletes something. Safe to
-- run more than once.

drop trigger if exists feedback_limit on feedback;
drop function if exists enforce_feedback_limit();

create or replace function block_feedback_when_full() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if (select count(*) from feedback) >= 20 then
    raise exception 'Feedback board is full (20 entries) -- please contact the admin.'
      using errcode = 'P0001';
  end if;
  return new;
end $$;

drop trigger if exists feedback_cap on feedback;
create trigger feedback_cap
  before insert on feedback
  for each row execute function block_feedback_when_full();
