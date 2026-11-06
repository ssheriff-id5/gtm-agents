# Deal owner sync: Technical Owner, Partnership Owner, Sales Engineer

**Source of truth: the Account.** Deals carry read-only mirrors of three Account fields,
kept in sync by two workflow rules. Nobody edits them on the Deal.

| Deal field (label / API name)          | Type        | Synced from Account field                          |
|----------------------------------------|-------------|----------------------------------------------------|
| Technical Owner / `Technical_Owner`    | User lookup | Technical Account Owner / `Technical_Account_Owner` |
| Partnership Owner / `Partnership_Owner`| User lookup | Partnership Owner / `Additional_Commercial_Owner`  |
| Sales Engineer / `Sales_Engineer`      | User lookup | Sales Engineer / `Sales_Engineer`                  |

> Confirm the API names Zoho generates after you create the fields (Setup → Developer Hub → APIs → API names → Deals).
> If they differ, update the `FIELD_MAP` in each function below and the column list in
> `.claude/skills/pipeline-tracker/SKILL.md`.

Closed stages are skipped by the Account-side sync: any Stage starting with `Closed`
(`Closed won`, `Closed Lost`, `Closed won - Canceled`, `Closed won - Did Not Renew`).
Closed deals keep the owners they had when they closed. This is deliberate, so history isn't rewritten.

## 1. Create the fields (Setup → Customization → Modules and Fields → Deals)
1. Add three **User** (lookup) fields with the labels above. Help text:
   *"Synced from the Account. Edit it on the Account."*
2. Field permissions: **read-only for every profile**. The functions run as admin and can still write.
3. Add them to the Deal layout(s) next to Deal Owner.

## 2. Function A: Deal → pull from its Account
Setup → Developer Hub → Functions → New (Category: Automation). Argument: `dealId` (Long), mapped to Deals → Deal Id.

```deluge
void automation.sync_deal_owners_from_account(Long dealId)
{
	FIELD_MAP = {"Technical_Owner":"Technical_Account_Owner","Partnership_Owner":"Additional_Commercial_Owner","Sales_Engineer":"Sales_Engineer"};
	deal = zoho.crm.getRecordById("Deals",dealId);
	acct = deal.get("Account_Name");
	upd = Map();
	if(acct == null)
	{
		for each  dealField in FIELD_MAP.keys()
		{
			upd.put(dealField,null);
		}
	}
	else
	{
		a = zoho.crm.getRecordById("Accounts",acct.get("id"));
		for each  dealField in FIELD_MAP.keys()
		{
			u = a.get(FIELD_MAP.get(dealField));
			upd.put(dealField,if(u == null,null,u.get("id")));
		}
	}
	// Empty trigger list = don't fire workflows again (prevents loops).
	resp = zoho.crm.updateRecord("Deals",dealId,upd,{"trigger":List()});
	info resp;
}
```

**Workflow rule A**: Module Deals. When: *Create or Edit*, with "Repeat this workflow whenever a deal is edited" **on**,
condition: **Account Name is modified** OR it's a create. (Simplest: two rules, *On Create* and *On Edit → Account Name modified*.)
Instant action: Function A.

## 3. Function B: Account → push to its open Deals
Argument: `accountId` (Long), mapped to Accounts → Account Id.

```deluge
void automation.push_account_owners_to_deals(Long accountId)
{
	FIELD_MAP = {"Technical_Owner":"Technical_Account_Owner","Partnership_Owner":"Additional_Commercial_Owner","Sales_Engineer":"Sales_Engineer"};
	a = zoho.crm.getRecordById("Accounts",accountId);
	upd = Map();
	for each  dealField in FIELD_MAP.keys()
	{
		u = a.get(FIELD_MAP.get(dealField));
		upd.put(dealField,if(u == null,null,u.get("id")));
	}
	// Up to 1,000 related deals (5 pages x 200).
	for each  page in {1,2,3,4,5}
	{
		deals = zoho.crm.getRelatedRecords("Deals","Accounts",accountId,page,200);
		for each  d in deals
		{
			stage = ifnull(d.get("Stage"),"");
			if(!stage.startsWith("Closed"))
			{
				zoho.crm.updateRecord("Deals",d.get("id"),upd,{"trigger":List()});
			}
		}
		if(deals.size() < 200)
		{
			break;
		}
	}
}
```

**Workflow rule B**: Module Accounts. When: *Edit*, repeat on every edit, condition: **Technical Account Owner OR Partnership Owner OR Sales Engineer is modified**.
Instant action: Function B.

## 4. Backfill existing deals (one-off)
Run Function B once per Account that has open deals. Easiest: a standalone function that loops
`zoho.crm.getRecords("Accounts", page, 200)` and calls `automation.push_account_owners_to_deals(acc.get("id").toLong())`.
Run it in batches if it hits the Deluge execution limit. After that, spot-check 5 deals against their Accounts.

## 5. Test
1. Change the Technical Account Owner on a test Account → its open Deals update and closed ones don't.
2. Create a Deal on that Account → all three fields are filled.
3. Move a Deal to a different Account → the fields switch.
4. Clear a field on the Account → it clears on the open Deals.
5. As a non-admin user, confirm you can't edit the three fields on a Deal.
