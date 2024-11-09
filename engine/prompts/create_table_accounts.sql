USE [GAIT]
GO

/****** Object:  Table [dbo].[Accounts]    Script Date: 3/29/2024 10:59:28 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE TABLE [dbo].[Accounts](
	[AccountId] [uniqueidentifier] NOT NULL,
	[ContactId] [uniqueidentifier] NOT NULL,
	[RoleTypeId] [uniqueidentifier] NOT NULL,
	[Description] [varchar](50) NULL,
	[Notes] [varchar](max) NULL,
	[TaxId] [varchar](10) NULL,
	[RepresentingAccountId] [uniqueidentifier] NULL,
	[IsMaster] [bit] NOT NULL,
	[ActiveStartDate] [smalldatetime] NOT NULL,
	[ActiveEndDate] [smalldatetime] NULL,
	[LegacyPk] [int] NULL,
	[LegacyEntity] [varchar](15) NULL,
	[CreateDate] [datetime] NOT NULL,
	[PrimaryLocationId] [uniqueidentifier] NULL,
	[PrimaryPhoneId] [uniqueidentifier] NULL,
	[PrimaryEmailAddressId] [uniqueidentifier] NULL,
	[Code] [varchar](8) NULL,
	[ServiceAgreementTypeId] [uniqueidentifier] NULL,
	[AcquisitionCompanyId] [uniqueidentifier] NULL,

CONSTRAINT [PK_Accounts] PRIMARY KEY CLUSTERED 
(
	[AccountId] ASC
)WITH (PAD_INDEX = OFF, STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON, FILLFACTOR = 100) ON [PRIMARY]
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY]
GO
/*
ALTER TABLE [dbo].[Accounts] ADD  CONSTRAINT [DF_Accounts_AccountId]  DEFAULT ([dbo].[udf_SeqGuid](newid(),getdate())) FOR [AccountId]
GO

ALTER TABLE [dbo].[Accounts] ADD  CONSTRAINT [DF_Accounts_IsMaster]  DEFAULT ((1)) FOR [IsMaster]
GO

ALTER TABLE [dbo].[Accounts] ADD  CONSTRAINT [DF_Accounts_ActivateDate]  DEFAULT ('19000101') FOR [ActiveStartDate]
GO

ALTER TABLE [dbo].[Accounts] ADD  CONSTRAINT [DF_Accounts_CreateDate]  DEFAULT (getdate()) FOR [CreateDate]
GO

ALTER TABLE [dbo].[Accounts]  WITH CHECK ADD  CONSTRAINT [FK_Accounts_Accounts] FOREIGN KEY([RepresentingAccountId])
REFERENCES [dbo].[Accounts] ([AccountId])
GO

ALTER TABLE [dbo].[Accounts] CHECK CONSTRAINT [FK_Accounts_Accounts]
GO

ALTER TABLE [dbo].[Accounts]  WITH CHECK ADD  CONSTRAINT [FK_Accounts_Contacts] FOREIGN KEY([ContactId])
REFERENCES [dbo].[Contacts] ([ContactId])
GO

ALTER TABLE [dbo].[Accounts] CHECK CONSTRAINT [FK_Accounts_Contacts]
GO

ALTER TABLE [dbo].[Accounts]  WITH CHECK ADD  CONSTRAINT [CK_AccountsActiveDate] CHECK  (([ActiveEndDate] IS NULL OR [ActiveStartDate]<[ActiveEndDate]))
GO

ALTER TABLE [dbo].[Accounts] CHECK CONSTRAINT [CK_AccountsActiveDate]
GO
*/


