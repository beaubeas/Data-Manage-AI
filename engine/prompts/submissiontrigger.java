trigger CreateOpportunityOnSubmission on Submission__c (after insert) {
    List<Opportunity> newOpportunities = new List<Opportunity>();
    List<OpportunityLineItem> newOpportunityLineItems = new List<OpportunityLineItem>();

    for (Submission__c submission : Trigger.new) {
        // Query the related Group__c record
            Group__c relatedGroup = [SELECT Id, Name FROM Group__c WHERE Id = :submission.Group_Name__c LIMIT 1];

        // Create the new Opportunity
        Opportunity newOpp = new Opportunity();
        newOpp.RecordTypeId = '012DL000006WtUGYA0'; // Use the specific RecordTypeId for Opportunities
        newOpp.Pricebook2Id = '01sDL00000849CWYAY'; // Use the specific Pricebook2Id for Opportunities
        newOpp.Name =submission.Renewal_Date__c+' '+submission.Coverage_Type__c +' '+ relatedGroup.Name;
        newOpp.StageName = 'Prospecting'; // Set the appropriate StageName
        newOpp.CloseDate = submission.Date_Closed__c;  //Date.today().addMonths(3); // Set the appropriate CloseDate
        newOpp.Group__c = relatedGroup.Id;
        newOpportunities.add(newOpp);

        // Create the OpportunityLineItem
        OpportunityLineItem oli = new OpportunityLineItem();
        oli.Quantity = 1;
        oli.UnitPrice = submission.premium__c; // Set the appropriate UnitPrice

        // Set PriceBookEntryId and Product2Id based on the coverage type from the Submission__c
        String coverageType = submission.Coverage_Type__c;
        if (coverageType != null) {
            if (coverageType.equalsIgnoreCase('Medical')) {
                oli.PriceBookEntryId = '01uDL00000r0tbNYAQ';
                oli.Product2Id = '01tDL00000I27u4YAB';
            } else if (coverageType.equalsIgnoreCase('Dental')) {
                oli.PriceBookEntryId = '01uDL00000r0uEWYAY';
                oli.Product2Id = '01tDL00000I28P2YAJ';
            } else if (coverageType.equalsIgnoreCase('Life')) {
                oli.PriceBookEntryId = '01uDL00000r0uEqYAI';
                oli.Product2Id = '01tDL00000I27u4YAB';
            } else if (coverageType.equalsIgnoreCase('WS Gap/Hospital' ||
		       coverageType.equalsIgnoreCase('WS Disability') ||
		       coverageType.equalsIgnoreCase('WS Accident') ||
		       coverageType.equalsIgnoreCase('WS Accident') ||
		       coverageType.equalsIgnoreCase('WS Cancer Care') ||
		       coverageType.equalsIgnoreCase('WS Gap/Hospital')) { 
                oli.PriceBookEntryId = '01uDL00000r0uF0YAI';
                oli.Product2Id = '01tDL00000I28PHYAZ';
            } else if (coverageType.equalsIgnoreCase('VIS') || coverageType.equalsIgnoreCase('Vision')) {
                oli.PriceBookEntryId = '01uDL00000r0uEgYAI';
                oli.Product2Id = '01tDL00000I28P7YAJ';
            } else if (coverageType.equalsIgnoreCase('STD')) {
                oli.PriceBookEntryId = '01uDL00000r0zLHYAY';
                oli.Product2Id = '01tDL00000I2ESAYA3';
            } else if (coverageType.equalsIgnoreCase('LTD')) {
                oli.PriceBookEntryId = '01uDL00000r0zLRYAY';
                oli.Product2Id = '01tDL00000I2ESFYA3';
            }
        }
        newOpportunityLineItems.add(oli);
    }

    // Insert the new Opportunity records
    insert newOpportunities;

    // Associate the OpportunityLineItems with the newly created Opportunities
    for (Integer i = 0; i < newOpportunities.size(); i++) {
        newOpportunityLineItems[i].OpportunityId = newOpportunities[i].Id;
    }

    // Insert the new OpportunityLineItem records
    insert newOpportunityLineItems;
}
