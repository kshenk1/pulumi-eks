#!/usr/bin/env bash

user_values="support/${USER}-values.yaml"

[[ ! -f "support/ci-example-values.yaml" ]] && { 
    echo "Error: support/ci-example-values.yaml not found. Please ensure you are running this script from the root of the repository and that the file exists." >&2
    exit 1
}

export storage_class_name="$(pulumi stack output storage_class_name)"
export hosted_zone_name="$(pulumi stack output zone_name)"
export certificate_arn="$(pulumi stack output certificate_arn)"

###############################################################################
## We need to construct a string of cidr addresses to let the ALB know who can visit
inbound_cidrs=""

myip="$(pulumi config get myip)"
[[ -n "$myip" ]] && {
    inbound_cidrs="${myip}"
}

additional_alb_cidrs="$(pulumi config get additional_alb_access_cidrs)"
[[ -n "$additional_alb_cidrs" ]] && {
    _alb_cidrs="$(echo "$additional_alb_cidrs" | jq -r 'join(",")')"
    [[ -n "$inbound_cidrs" ]] && inbound_cidrs="${inbound_cidrs},"
    inbound_cidrs="${inbound_cidrs},$_alb_cidrs"
}

export inbound_cidrs
###############################################################################

[[ -f "$user_values" ]] && { 
    echo "Warning: $user_values already exists"
    read -p "Do you want to overwrite it? (y/n) " answer
    
    answer=$(echo "$answer" | tr '[:upper:]' '[:lower:]')
    if [[ "$answer" != "y" ]]; then 
        echo "Aborting. Move $user_values and re-run this script to generate a new one."
        exit 0
    fi
    rm "$user_values"
}

envsubst < support/ci-example-values.yaml > $user_values
file $user_values
echo "This should be considered a starting point. You may need to further customize $user_values before using it to install CloudBees CI. Please review the file and make any necessary adjustments before proceeding with the installation."