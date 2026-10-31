using GPV.ProductTimeFlow.Domain;

namespace GPV.ProductTimeFlow.UnitTests.Domain;

public class WorkCalendarTests
{
    [Fact]
    public void Default_calendar_counts_monday_to_friday()
    {
        var cal = WorkCalendar.Default;
        // 2026-03-09 lunes … 2026-03-22 domingo: dos semanas completas.
        Assert.Equal(10, cal.CountWorkingDays(new DateOnly(2026, 3, 9), new DateOnly(2026, 3, 22)));
        Assert.Equal(0, cal.CountWorkingDays(new DateOnly(2026, 3, 14), new DateOnly(2026, 3, 15))); // sábado-domingo
        Assert.Equal(1, cal.CountWorkingDays(new DateOnly(2026, 3, 13), new DateOnly(2026, 3, 13))); // viernes
    }

    [Fact]
    public void Configured_holidays_are_excluded()
    {
        var holiday = new DateOnly(2026, 3, 16); // lunes festivo
        var cal = new WorkCalendar(WorkCalendar.ParseWorkingDays("1,2,3,4,5"), [(holiday, "Natalicio de Benito Juárez")]);

        Assert.True(cal.IsHoliday(holiday));
        Assert.False(cal.IsWorkingDay(holiday));
        Assert.Equal(4, cal.CountWorkingDays(new DateOnly(2026, 3, 16), new DateOnly(2026, 3, 20)));
        var names = cal.HolidaysBetween(new DateOnly(2026, 3, 1), new DateOnly(2026, 3, 31));
        Assert.Single(names);
        Assert.Contains("16/03/2026", names[0]);
    }

    [Fact]
    public void End_before_start_returns_zero()
    {
        Assert.Equal(0, WorkCalendar.Default.CountWorkingDays(new DateOnly(2026, 3, 20), new DateOnly(2026, 3, 16)));
    }

    [Fact]
    public void Duplicate_holiday_dates_do_not_throw()
    {
        var d = new DateOnly(2026, 12, 25);
        var cal = new WorkCalendar(WorkCalendar.ParseWorkingDays("1,2,3,4,5"), [(d, "Navidad"), (d, "Duplicado")]);
        Assert.True(cal.IsHoliday(d));
    }

    [Fact]
    public void ParseWorkingDays_maps_1_to_monday_and_7_to_sunday()
    {
        var days = WorkCalendar.ParseWorkingDays("1,2,3,4,5,6,7");
        Assert.Equal([DayOfWeek.Monday, DayOfWeek.Tuesday, DayOfWeek.Wednesday, DayOfWeek.Thursday, DayOfWeek.Friday, DayOfWeek.Saturday, DayOfWeek.Sunday], days);
    }

    [Fact]
    public void ParseWorkingDays_ignores_invalid_entries_whitespace_and_duplicates()
    {
        var days = WorkCalendar.ParseWorkingDays(" 1, 1 ,x, 0, 8, ,6 ");
        Assert.Equal([DayOfWeek.Monday, DayOfWeek.Saturday], days);
        Assert.Empty(WorkCalendar.ParseWorkingDays(""));
    }

    [Fact]
    public void Custom_working_days_including_saturday()
    {
        var cal = new WorkCalendar(WorkCalendar.ParseWorkingDays("1,2,3,4,5,6"), []);
        Assert.Equal(6, cal.CountWorkingDays(new DateOnly(2026, 3, 9), new DateOnly(2026, 3, 15)));
    }
}
