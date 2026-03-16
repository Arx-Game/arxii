# Kudos-to-XP Claiming UI Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let players convert kudos to XP from the XP/Kudos page via a dialog with confirmation.

**Architecture:** New POST endpoint on backend, dialog component on existing XpKudosPage. Account-level XP only (no character targeting).

**Tech Stack:** Django REST Framework, React, React Query, shadcn Dialog + AlertDialog.

---

## Backend

### POST `/api/progression/claim-kudos/`

**Request:** `{ "claim_category_id": number, "amount": number }`

**Response (200):** Updated account progression data (same shape as GET `/api/progression/account/`) so the frontend can refresh in one round-trip.

**Errors:** Standard DRF validation — 400 with `{ "detail": "..." }` or field-level errors.

**Validation:**
- amount > 0
- amount <= current available kudos
- claim_category exists and is active
- Conversion yields non-zero XP

### Implementation

New `ClaimKudosView(APIView)` in `progression/views.py` with `permission_classes = [IsAuthenticated]`. Uses `claim_kudos_for_xp` service. Returns refreshed progression data via existing serializer.

Register at `/api/progression/claim-kudos/` in `progression/urls.py`.

---

## Frontend

### Claim Dialog (on Kudos balance card)

- "Convert to XP" button on Kudos card
- Opens Dialog with:
  - Current kudos balance
  - Number input + "Max" button
  - Live preview: "X kudos → Y XP"
  - "Convert" button (disabled when invalid)
- Convert button triggers AlertDialog confirmation: "Convert X kudos to Y XP? This cannot be undone."
- On confirm: POST via useMutation, invalidate account-progression query
- On success: close dialog, balances refresh automatically

### Files changed

- `frontend/src/progression/api.ts` — add `claimKudosForXP` fetch function
- `frontend/src/progression/queries.ts` — add `useClaimKudosMutation` hook
- `frontend/src/progression/XpKudosPage.tsx` — add button + dialog
- `src/world/progression/views.py` — add `ClaimKudosView`
- `src/world/progression/urls.py` — register new endpoint

---

### Task 1: Add backend POST endpoint

**Files:**
- Modify: `src/world/progression/views.py`
- Modify: `src/world/progression/urls.py`

**Step 1: Add ClaimKudosView**

Add to `views.py`:

```python
class ClaimKudosView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        claim_category_id = request.data.get("claim_category_id")
        amount = request.data.get("amount")

        # Validate inputs
        if not claim_category_id or not amount:
            return Response(
                {"detail": "claim_category_id and amount are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return Response(
                {"detail": "amount must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            claim_category = KudosClaimCategory.objects.get(
                id=claim_category_id, is_active=True,
            )
        except KudosClaimCategory.DoesNotExist:
            return Response(
                {"detail": "Invalid or inactive claim category."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            claim_kudos_for_xp(
                account=request.user,
                amount=amount,
                claim_category=claim_category,
            )
        except InsufficientKudosError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Return refreshed progression data
        return _build_progression_response(request)
```

Extract the existing GET response logic from AccountProgressionView into a shared `_build_progression_response(request)` helper.

**Step 2: Register URL**

Add to `urls.py`:
```python
path("claim-kudos/", ClaimKudosView.as_view(), name="claim-kudos"),
```

**Step 3: Test**

Run: `arx test world.progression`

**Step 4: Commit**

---

### Task 2: Add frontend API + mutation

**Files:**
- Modify: `frontend/src/progression/api.ts`
- Modify: `frontend/src/progression/queries.ts`

**Step 1: Add fetch function to api.ts**

```typescript
export async function claimKudosForXP(
  claimCategoryId: number,
  amount: number,
): Promise<AccountProgressionData> {
  return apiFetch('/api/progression/claim-kudos/', {
    method: 'POST',
    body: JSON.stringify({ claim_category_id: claimCategoryId, amount }),
  });
}
```

**Step 2: Add mutation hook to queries.ts**

```typescript
export function useClaimKudosMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimCategoryId, amount }: { claimCategoryId: number; amount: number }) =>
      claimKudosForXP(claimCategoryId, amount),
    onSuccess: (data) => {
      queryClient.setQueryData(['account-progression'], data);
    },
  });
}
```

**Step 3: Run typecheck**

Run: `pnpm typecheck`

**Step 4: Commit**

---

### Task 3: Add claim dialog to XpKudosPage

**Files:**
- Modify: `frontend/src/progression/XpKudosPage.tsx`

**Step 1: Add "Convert to XP" button on Kudos card**

**Step 2: Add ClaimKudosDialog component**

Local component with:
- Number input + Max button
- Live preview line
- Convert button that opens AlertDialog confirmation
- On confirm: call mutation, close on success

**Step 3: Run typecheck + lint**

**Step 4: Commit**
