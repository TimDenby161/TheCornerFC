#!/usr/bin/env bash
# The C# site's home in Azure (site/, T-048): one App Service plan, size B1 (Linux, UK South,
# about $13 a month, the owner's yes on 2026-10-18), holding two web apps, the live site and
# staging. The owner runs it once, signed in with `az login`; running it again changes nothing
# that is already as it should be.
#
#   1. Policies on the subscription (the owner's choice, 2026-10-19): nothing may be created in
#      it but App Service plans, web apps and their certificates, and a plan only as one B1. A
#      bigger plan, a second instance, a database or a virtual machine is refused, so the bill
#      can't grow past the B1. The budget's emails are the second guard.
#   2. The resource group, the plan and the two apps: .NET 10, always on, https only, TLS 1.2 at
#      least, no FTP and no password-based publishing.
#   3. Each app answers Cloudflare only (its published address ranges), so visitors come through
#      Cloudflare's bot block, cache and, for staging, Access. Deploys use the separate
#      management address, which needs an Azure sign-in.
set -euo pipefail

RG=thecornerfc
LOCATION=uksouth
PLAN=thecornerfc-plan
APPS=("thecornerfc:production" "thecornerfc-staging:staging")

sub=$(az account show --query id -o tsv)
echo "Subscription: $(az account show --query name -o tsv) (signed in as $(az account show --query user.name -o tsv))"

# 1. What the subscription may hold
az provider register --namespace Microsoft.Web --wait
az policy assignment create --name only-the-site --display-name "Only the site's App Service" \
  --policy a08ec900-254a-4555-9bf5-e42af04b5c5c --scope "/subscriptions/$sub" \
  --params '{"listOfResourceTypesAllowed": {"value": ["Microsoft.Web/serverfarms", "Microsoft.Web/sites", "Microsoft.Web/certificates"]}}' \
  --output none
az policy definition create --name only-one-b1 --display-name "App Service plans: one B1 only" --mode Indexed \
  --rules '{"if": {"allOf": [{"field": "type", "equals": "Microsoft.Web/serverfarms"},
             {"anyOf": [{"field": "Microsoft.Web/serverfarms/sku.name", "notEquals": "B1"},
                        {"field": "Microsoft.Web/serverfarms/sku.capacity", "greater": 1}]}]},
            "then": {"effect": "deny"}}' \
  --output none
az policy assignment create --name only-one-b1 --display-name "App Service plans: one B1 only" \
  --policy only-one-b1 --scope "/subscriptions/$sub" --output none

# 2. The plan and the apps
az group create --name "$RG" --location "$LOCATION" --output none
az appservice plan create --resource-group "$RG" --name "$PLAN" --location "$LOCATION" --sku B1 --is-linux --output none

cloudflare=$(curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6)
for entry in "${APPS[@]}"; do
  app=${entry%%:*} env=${entry##*:}
  az webapp show --resource-group "$RG" --name "$app" --output none 2>/dev/null \
    || az webapp create --resource-group "$RG" --plan "$PLAN" --name "$app" --runtime "DOTNETCORE:10.0" --output none
  az webapp update --resource-group "$RG" --name "$app" --https-only true --output none
  az webapp config set --resource-group "$RG" --name "$app" --always-on true --ftps-state Disabled \
    --min-tls-version 1.2 --http20-enabled true --output none
  az webapp config appsettings set --resource-group "$RG" --name "$app" --settings "SITE_ENV=$env" --output none
  for kind in ftp scm; do
    az resource update --resource-group "$RG" --namespace Microsoft.Web --resource-type basicPublishingCredentialsPolicies \
      --parent "sites/$app" --name "$kind" --set properties.allow=false --output none
  done

  # 3. Cloudflare only (the management address keeps its own rules: it needs an Azure sign-in)
  az webapp config access-restriction set --resource-group "$RG" --name "$app" --use-same-restrictions-for-scm-site false --output none
  n=100
  while read -r range; do
    [ -n "$range" ] || continue
    rule="cloudflare-$n"
    az webapp config access-restriction show --resource-group "$RG" --name "$app" --query "ipSecurityRestrictions[?name=='$rule']" -o tsv | grep -q . \
      || az webapp config access-restriction add --resource-group "$RG" --name "$app" --rule-name "$rule" \
           --action Allow --ip-address "$range" --priority "$n" --output none
    n=$((n + 1))
  done <<< "$cloudflare"
  echo "$app ($env): https://$app.azurewebsites.net, Cloudflare's addresses only"
done

echo "Done. The policies take up to 30 minutes to start refusing. Nothing is deployed yet."
