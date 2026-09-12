# Camera settings - user guide

For the person on site and the person at the desk. Two scripts, one spreadsheet, no installing.
How it is built, and why: `ARCHITECTURE.md`.

    1  On site     run  export.bat      reads every camera into a zip. Changes nothing.
    2  At a desk   open settings.csv from the zip in Excel, change what needs changing, save.
    3  On site     run  import.bat      writes only the cameras you changed, with a way back.

If you only ever read this page: the export changes nothing, the import shows you exactly what it
will change and waits for you to type the site name before it touches a camera, and the zip it
leaves behind holds the file that puts everything back.

---

## 1. What you need

- A Windows machine on the camera network, with Motorola's **Camera Configuration Tool** installed
  (version 2.16 or newer)
- The camera login - the username and password the cameras themselves accept
- The address range the cameras sit in, first address to last
- The two scripts

Both scripts ask Windows for administrator permission when they start. Answer **Yes**. Older
versions of the Motorola tool need it and crash without it.

## 2. Export, on site

1. Double-click **`export.bat`**. Answer Yes to the administrator prompt.
2. Fill the form. The cursor steps down as you press Enter:

       Site name                 :   
       Start IP                  :   
       End IP                    :   
       Camera username           :   
       Camera password           :
       HTTP port                 : 80       press Enter to keep the value shown
       HTTPS port                : 443

3. Wait. The screen counts the addresses it checks, then runs the Camera Configuration Tool
   once per subnet that holds a camera. One subnet takes about 35 seconds. A whole large site takes over an hour
   and asks you first if the range is big.
4. Read the last screen. It says how many cameras were read, whether any need attention, and
   where the zip is:

       Send back        : C:\...\<Site name>_ACC_Camera_Settings_11_09_26.zip

**What is in the zip**

    settings.csv      one row per camera - the file to open in Excel
    analytics.csv     one row per camera head - the analytics settings, rarely needed
    backup            the file exactly as the Camera Configuration Tool wrote it. No file
                      extension on purpose, so a double-click does not open it in Excel
    camera.log        which cameras answered and which did not, subnet by subnet
    console.log       Camera Configuration Tool's output
    import.log        the settings the export ran with, the counts and the result

If a subnet is flagged INCOMPLETE in camera.log, run the export again for just that subnet - its
first and last address as the Start and End IP - and send that zip too.

## 3. Edit, at a desk

1. Unzip the export somewhere you can find again. Keep the files together - the import wants
   the backup file from the same folder later.
2. Open **`settings.csv`** in Excel. One row per camera; the first row names the columns. The
   ones a rename touches are **Name** and **Location**. Make your changes.
3. **File, Save.** When Excel asks whether to keep the CSV format, say yes. Close Excel.

Rules that keep you out of trouble:

- **Never change MacAddress.** It is how the camera is found again. Everything else in the row
  can change, but this one cell must not.
- **Change only what you mean to.** Every cell that differs from the site is treated as a change
  and shown on screen before anything happens. Serial numbers, firmware, model, manufacturer and
  the date are for reading only; the import ignores them.
- **Type values as a person would.** `true` or `TRUE` in a True/False column, `1920x1080` for a
  resolution, `h264` for an encoding - the import tidies them. A value a column cannot read at
  all is left alone.
- **Changing an address gives the camera that address permanently.** Type a new `IpAddress`
  and the tool switches DHCP off for that camera and brings its mask and gateway along from the
  export, because an address only works with those. Change `SubnetMask` or `DefaultGateway` too if
  this camera needs different ones. An address you are not changing is not sent at all.
- **Cameras that move address are written last**, after everything else, and the plan lists them
  with their old and new address before you type the site name. Read that list: a camera that does
  not come back at its new address cannot be reached to put it back either.
- **Blank means leave it alone.** Do not blank a cell to reset a setting; put in the value you
  want.
- **Fewer rows is fine.** A file holding only the cameras you changed imports just as well as
  the whole file.
- **Do not open the backup file in Excel.** Excel breaks that file on save.
- **Passwords.** The AdminPassword and SecondaryAdminPassword columns are empty on export. A value
  typed there sets the camera's password on import. Leave them empty unless that is the job.
- `analytics.csv` holds the analytics settings, one row per camera head, with the coded values
  written as words (Outdoor, Colour, VAL - video analytics). Edit it the same way if the job
  needs it; leave it out and every head stays as it is.

Send the folder - `settings.csv` and the backup file at least - back to site.

## 4. Import, on site

1. Put the edited `settings.csv` and the backup file from the export in one folder on the machine.
2. **Drag `settings.csv` onto `import.bat`.** Answer Yes to the administrator prompt.
   The form opens with the file already in place:

       Site name                 :   type the site name - you will type it again to confirm
       Settings file to import   : C:\...\settings.csv      the file you dropped
       Rollback (blank = export) : C:\...\backup     offered when it sits beside the file
       Camera username           :
       Camera password           :
       HTTP port                 : 80
       HTTPS port                : 443

   The **rollback** is the site as it was when the export ran. If the backup file is there it is offered;
   press Enter to keep it. If you do not have it, leave the field blank and the script reads every
   camera in the file first before going on.
3. **Read the plan.** The screen shows what will change, camera by camera:

       Settings to change   : 2   (Name 2)
       Cameras to change    : 2   (every other camera is left alone - not written to, not logged into)
       CCT runs             : 1 to import, 1 to prove it - roughly 30 s in all
         192.168.1.161-192.168.1.162

         C1515 (192.168.1.161)   Name
             from  'acc/C1515 - Front Entry'
             to    'acc/C1515 - Rear Entry'

   Only the cameras listed are touched. If a cell could not be read it is listed under **LEFT AS THEY ARE**, with
   the reason, and that camera keeps what it has for that setting. Anything changing address is
   listed under **NETWORK CHANGES**, with its old and new address, and is written last.
4. **Two questions.** `Write this change list to a CSV beside the script? [y/N]` - y gives you a
   file to keep or forward; the list is in the zip either way. Then:

       Type the site name exactly as above to go ahead, or press Enter to stop :

   Enter stops with nothing changed. If the file sets passwords, a second word - ROTATE - is asked
   for as well.
5. Wait. One short run per group of changed cameras, then the same cameras are read back
   to prove it. Two cameras take well under a minute.
6. Read the verdict:

       SUCCESS       every change in the file is now on the cameras
       PARTIAL       something did not take - camera.log in the zip names it. Run again with the same
                     file; it changes only what still differs
       NOTHING TO DO the cameras already hold everything in the file
       STOPPED       a gate stopped it before anything was written - the screen says which

   Then send back the zip named on the screen.

**What is in the import zip**

    rollback          every camera as it was before. Import this file to undo the change. No file
                      extension, like the backup file - do not open it in Excel
    settings.csv      what the Motorola tool was given - only the cameras that changed
    edited.csv        your file, exactly as you dropped it
    after.csv         the changed cameras as they are now
    changes.csv       the change list, one row per setting
    camera.log        what was intended, what did not take, one table per phase
    console.log       the Motorola tool's own output
    import.log        the settings the run used, the counts, the verdict

## 5. Undoing a change

Drag **`rollback`** from the import zip onto `import.bat` and run it exactly as
above. It is an ordinary settings file holding every camera as it was, so the plan shows the
changes reversed and only those cameras are touched again.

## 6. When it stops, and what to do

Every stop screen says three things: what happened, that nothing was changed, and what to do.
The common ones:

| Screen says | It means | Do this |
|---|---|---|
| COULD NOT START - Camera Configuration Tool not found | Camera Configuration Tool is not installed where the script expects | Install the Camera Configuration Tool, 2.16 or newer, and run again |
| COULD NOT START - permission was declined | The administrator prompt was answered No or closed | Run again and answer Yes |
| STOPPED - the questions went unanswered | A form field was left wrong five times | Run again and fill each field |
| That is not a settings file | The file dropped is not an export's `settings.csv` or backup file | Check the file opens in Excel with MacAddress and Name in its first row |
| DID NOT ANSWER - the import stops here | A camera in your file did not answer when the site was read | Check that camera is online, then run again with the same file |
| NOT IN THE ROLLBACK FILE | Your file names a camera the rollback does not have | Use the backup file from the export your file came from, or leave the rollback blank |
| LEFT AS THEY ARE | A cell held something the column cannot read | Not a stop. The camera keeps what it has for that cell; fix the cell and run again if it was meant |
| STOPPED at the confirmation | Enter was pressed at the site name, or it was typed wrongly three times | Run again and type the site name exactly as shown |
| PARTIAL - settings did not take | The camera accepted the write and kept its old value | Open camera.log in the zip; run again with the same file. If it happens twice, send the zip |
